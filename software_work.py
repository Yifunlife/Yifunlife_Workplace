"""Internal R&D intake, engineering assignments and explicit work-session timing."""
import hashlib,json,time
from datetime import datetime,date
from zoneinfo import ZoneInfo
import core as c,centers,column_permissions as cp,runtime_config
STATES={'received':'待安排','queued':'已排期','in_progress':'开发中','paused':'已暂停','review':'待验收','completed':'已完成','cancelled':'已取消'}
def init(db):
 db.execute('CREATE TABLE IF NOT EXISTS software_team_slots(slot INTEGER PRIMARY KEY CHECK(slot BETWEEN 1 AND 5),employee_id TEXT UNIQUE REFERENCES employees(id))')
 db.execute('''CREATE TABLE IF NOT EXISTS software_work_items(id TEXT PRIMARY KEY,number TEXT NOT NULL UNIQUE,title TEXT NOT NULL,brief TEXT NOT NULL,priority TEXT NOT NULL,state TEXT NOT NULL,owner_id TEXT REFERENCES employees(id),due_date TEXT,started_at REAL,completed_at REAL,result_reference TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL REFERENCES employees(id),created_at REAL NOT NULL,updated_at REAL NOT NULL,version INTEGER NOT NULL DEFAULT 1,request_id TEXT NOT NULL,request_hash TEXT NOT NULL,source_center TEXT NOT NULL DEFAULT 'product_rd',UNIQUE(created_by,request_id))''')
 db.execute('''CREATE TABLE IF NOT EXISTS software_work_sessions(id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES software_work_items(id),owner_id TEXT NOT NULL REFERENCES employees(id),started_at REAL NOT NULL,ended_at REAL,note TEXT NOT NULL DEFAULT '')''')
 db.execute('CREATE UNIQUE INDEX IF NOT EXISTS software_one_running_task ON software_work_sessions(task_id) WHERE ended_at IS NULL')
 db.execute('CREATE UNIQUE INDEX IF NOT EXISTS software_one_running_engineer ON software_work_sessions(owner_id) WHERE ended_at IS NULL')
 db.execute('''CREATE TABLE IF NOT EXISTS software_work_history(id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES software_work_items(id),actor_id TEXT NOT NULL REFERENCES employees(id),action TEXT NOT NULL,note TEXT NOT NULL,created_at REAL NOT NULL)''')
def scopes(db,user,write=False):
 result=[]
 for center in ('software','product_rd'):
  if center in centers.available(db,user) and cp.level(db,user,'center-'+center)>=(2 if write else 1):result.append(center)
 if not result:raise c.Problem('没有研发任务的使用权限',403)
 if write and runtime_config.read_only(user):raise c.Problem('共享账号仅可查看',403)
 return result

def overview(db,user):
 allowed=scopes(db,user);stamp=time.time();manager=user['role'] in ('admin','ceo');software='software' in allowed
 items=[]
 for raw in db.execute('SELECT * FROM software_work_items ORDER BY created_at DESC,id'):
  r=dict(raw)
  if not software and not manager and r['created_by']!=user['id']:continue
  r['elapsed_seconds']=sum(max(0,(s['ended_at'] if s['ended_at'] is not None else stamp)-s['started_at']) for s in db.execute('SELECT started_at,ended_at FROM software_work_sessions WHERE task_id=?',(r['id'],)))
  r['history']=[dict(h) for h in db.execute('SELECT actor_id,action,note,created_at FROM software_work_history WHERE task_id=? ORDER BY created_at',(r['id'],))];items.append(r)
 employees=[dict(r) for r in db.execute("SELECT id,name,role FROM employees WHERE status='active' AND role!='supplier' ORDER BY name,id")]
 engineers=[r for r in employees if centers.assigned(db,r,'software')]
 if not software and not manager:
  used={r['owner_id'] for r in items}|{r['created_by'] for r in items}|{user['id']}|{h['actor_id'] for r in items for h in r['history']};employees=[r for r in employees if r['id'] in used];engineers=[]
 workloads=[]
 for engineer in engineers:
  owned=[r for r in items if r['owner_id']==engineer['id'] and r['state'] not in ('completed','cancelled')];running=next((r for r in owned if r['state']=='in_progress'),None)
  seconds=0
  if running:seconds=sum(max(0,(s['ended_at'] if s['ended_at'] is not None else stamp)-s['started_at']) for s in db.execute('SELECT started_at,ended_at FROM software_work_sessions WHERE task_id=? AND owner_id=?',(running['id'],engineer['id'])))
  workloads.append({'id':engineer['id'],'name':engineer['name'],'open_count':len(owned),'running_task_id':running['id'] if running else None,'elapsed_seconds':seconds})
 return {'team_slots':[{'slot':i,'discipline':'hardware' if i==5 else 'software','label':'硬件工程师 1' if i==5 else '软件工程师 '+str(i),'employee_id':next((r['employee_id'] for r in db.execute('SELECT employee_id FROM software_team_slots WHERE slot=?',(i,))),None)} for i in range(1,6)] if software else [],'items':items,'employees':employees,'engineers':engineers,'workloads':workloads,'states':STATES,'server_time':stamp,'can_create':not runtime_config.read_only(user) and 'product_rd' in allowed and cp.level(db,user,'center-product_rd')==2,'can_assign':not runtime_config.read_only(user) and manager and software and cp.level(db,user,'center-software')==2,'user_id':user['id'],'can_review':not runtime_config.read_only(user) and any(cp.level(db,user,'center-'+v)==2 for v in allowed),'can_operate':not runtime_config.read_only(user) and 'software' in allowed and cp.level(db,user,'center-software')==2}

def note(db,user,key,action,text=''):
 db.execute('INSERT INTO software_work_history VALUES(?,?,?,?,?,?)',(c.uid(),key,user['id'],action,text,time.time()));c.audit(db,user,'software_work',key,action,{'note':text})
def execute(db,user,p):
 allowed=scopes(db,user,True);manager=user['role'] in ('admin','ceo');action=p.get('action')
 if action=='team-slots':
  if not manager or 'software' not in allowed:raise c.Problem('仅管理员或CEO可以安排团队岗位',403)
  slots=p.get('slots')
  if not isinstance(slots,list) or len(slots)!=5 or any(not isinstance(v,str) for v in slots):raise c.Problem('请提供四个软件岗位和一个硬件岗位')
  people=[v for v in slots if v]
  if len(set(people))!=len(people):raise c.Problem('同一成员不能重复占用岗位')
  for ident in people:
   employee=c.need(db,'employees',ident)
   if employee['status']!='active' or not centers.assigned(db,employee,'software'):raise c.Problem('请选择软件中心的在职成员')
  db.execute('DELETE FROM software_team_slots')
  for i,ident in enumerate(slots,1):
   if ident:db.execute('INSERT INTO software_team_slots VALUES(?,?)',(i,ident))
  c.audit(db,user,'software_team','team','更新软硬件团队岗位',{'slots':slots})
  return {'ok':True}
 if action=='create':
  if 'product_rd' not in allowed:raise c.Problem('请由产品研发中心提交需求，软件中心直接接收同一条记录',403)
  title=c.text(p.get('title'),'需求名称',limit=200);brief=c.text(p.get('brief'),'需求说明',limit=4000);priority=p.get('priority','normal')
  if priority not in ('normal','urgent'):raise c.Problem('优先级无效')
  request=c.text(p.get('request_id'),'提交编号',limit=100);digest=hashlib.sha256(json.dumps([title,brief,priority],ensure_ascii=False).encode()).hexdigest()
  existing=c.row(db,'SELECT id,request_hash FROM software_work_items WHERE created_by=? AND request_id=?',(user['id'],request))
  if existing:
   if existing['request_hash']!=digest:raise c.Problem('提交编号已被其他内容使用',409)
   return {'ok':True,'id':existing['id']}
  key=c.uid();number='SW-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')+'-'+key[:6].upper();stamp=time.time()
  db.execute("INSERT INTO software_work_items(id,number,title,brief,priority,state,created_by,created_at,updated_at,request_id,request_hash) VALUES(?,?,?,?,?,'received',?,?,?,?,?)",(key,number,title,brief,priority,user['id'],stamp,stamp,request,digest));note(db,user,key,'提交研发需求');return {'ok':True,'id':key}
 r=c.need(db,'software_work_items',p.get('id'))
 if 'software' not in allowed and not manager and r['created_by']!=user['id']:raise c.Problem('没有此研发需求的使用权限',403)
 if type(p.get('version')) is not int or p['version']!=r['version']:raise c.Problem('任务已被更新，请更新状态后重试',409)
 owner=r['owner_id']==user['id'] and 'software' in allowed;operator=owner or (manager and 'software' in allowed and bool(r['owner_id']));stamp=time.time();reason=c.text(p.get('note',''),'处理说明',required=False,limit=1000)
 def close_session():db.execute('UPDATE software_work_sessions SET ended_at=?,note=? WHERE task_id=? AND ended_at IS NULL',(stamp,reason,r['id']))
 if action=='assign':
  if not manager or 'software' not in allowed:raise c.Problem('仅管理员或 CEO 可以安排工程师',403)
  if r['state'] not in ('received','queued','paused'):raise c.Problem('请先暂停当前开发，再调整负责人')
  target=c.need(db,'employees',p.get('owner_id'))
  if target['status']!='active' or not centers.assigned(db,target,'software'):raise c.Problem('请选择已加入软件中心的在职工程师')
  due=p.get('due_date') or None
  if due:
   try:date.fromisoformat(due)
   except (ValueError,TypeError):raise c.Problem('目标日期不正确')
  db.execute("UPDATE software_work_items SET owner_id=?,due_date=?,state='queued' WHERE id=?",(target['id'],due,r['id']));label='安排工程师'
 elif action=='start':
  if not operator:raise c.Problem('请由负责人或管理员登记开始',403)
  if r['state'] not in ('queued','paused'):raise c.Problem('此状态不能开始开发')
  if db.execute('SELECT 1 FROM software_work_sessions WHERE owner_id=? AND ended_at IS NULL',(r['owner_id'],)).fetchone():raise c.Problem('请先暂停手上正在开发的任务，避免重复计时',409)
  db.execute('INSERT INTO software_work_sessions VALUES(?,?,?,?,NULL,\'\')',(c.uid(),r['id'],r['owner_id'],stamp));db.execute("UPDATE software_work_items SET state='in_progress',started_at=COALESCE(started_at,?) WHERE id=?",(stamp,r['id']));label='开始开发'
 elif action=='pause':
  if not operator:raise c.Problem('只有负责人或管理员可以登记暂停',403)
  if r['state']!='in_progress':raise c.Problem('任务不在开发中')
  if not reason:raise c.Problem('请说明暂停原因')
  close_session();db.execute("UPDATE software_work_items SET state='paused' WHERE id=?",(r['id'],));label='暂停开发'
 elif action=='submit':
  if not operator:raise c.Problem('只有负责人或管理员可以登记交付',403)
  if r['state'] not in ('in_progress','paused'):raise c.Problem('请先开始任务，再提交验收')
  reference=c.text(p.get('result_reference'),'成果位置或交付说明',limit=2000);close_session();db.execute("UPDATE software_work_items SET state='review',result_reference=? WHERE id=?",(reference,r['id']));label='提交验收'
 elif action in ('accept','return'):
  if not manager and r['created_by']!=user['id']:raise c.Problem('仅需求提出人或管理员可验收',403)
  if r['state']!='review':raise c.Problem('任务尚未提交验收')
  if action=='return' and not reason:raise c.Problem('请填写退回原因')
  db.execute('UPDATE software_work_items SET state=?,completed_at=? WHERE id=?',('completed' if action=='accept' else 'queued',stamp if action=='accept' else None,r['id']));label='验收完成' if action=='accept' else '退回修改'
 elif action=='cancel':
  if not manager:raise c.Problem('仅管理员可以取消任务',403)
  if r['state'] in ('completed','cancelled'):raise c.Problem('任务已经结束')
  if not reason:raise c.Problem('请填写取消原因')
  close_session();db.execute("UPDATE software_work_items SET state='cancelled' WHERE id=?",(r['id'],));label='取消研发任务'
 else:raise c.Problem('任务操作无效')
 db.execute('UPDATE software_work_items SET version=version+1,updated_at=? WHERE id=?',(stamp,r['id']));note(db,user,r['id'],label+('（管理员代记）' if manager and not owner and action in ('start','pause','submit') else ''),reason);return {'ok':True,'id':r['id']}
