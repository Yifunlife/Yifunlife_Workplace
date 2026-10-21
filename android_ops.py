"""Persistent Android operations, leases, configuration, events and webhook outbox.
Device-specific executors are explicitly gated by advertised adapter capabilities.
"""
import hashlib,hmac,http.client,ipaddress,json,secrets,socket,threading,time
from urllib.parse import urlsplit
import core as c

KINDS=('site','feature','entitlement','package','content','content_grant','alert_rule','webhook')
EVENTS=('device.offline','device.recovered','task.succeeded','task.failed','game.session_ended')
TASKS=('sync_config','collect_agent_logs','install_apk','rollback_apk','restart_app','reboot','sync_content')
DDL=[
'''CREATE TABLE IF NOT EXISTS android_resources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,product_id TEXT,customer_id TEXT,device_id TEXT,data TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS android_tasks(id TEXT PRIMARY KEY,device_id TEXT NOT NULL REFERENCES android_devices(id),kind TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,lease_hash TEXT,lease_until REAL,result TEXT NOT NULL DEFAULT '{}',created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS android_events(id TEXT PRIMARY KEY,device_id TEXT NOT NULL REFERENCES android_devices(id),event_id TEXT NOT NULL,category TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(device_id,event_id))''',
'''CREATE TABLE IF NOT EXISTS android_alerts(id TEXT PRIMARY KEY,rule_id TEXT NOT NULL,device_id TEXT NOT NULL REFERENCES android_devices(id),state TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,resolved_at TEXT)''',
'''CREATE UNIQUE INDEX IF NOT EXISTS android_alert_open ON android_alerts(rule_id,device_id) WHERE state='open' ''',
'''CREATE TABLE IF NOT EXISTS android_deliveries(id TEXT PRIMARY KEY,webhook_id TEXT NOT NULL REFERENCES android_resources(id),event_key TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL,lease_hash TEXT,lease_until REAL,last_result TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(webhook_id,event_key))''']

def init(db):
 for sql in DDL:db.execute(sql)
def dump(v):
 try:return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)
 except (TypeError,ValueError):raise c.Problem('资料包含无效的 JSON 数值或类型')
def txt(p,k,label,required=True,limit=200):return c.text(p.get(k,''),label,required=required,limit=limit)
def integer(p,k,minimum,maximum,default=None):
 v=p.get(k,default)
 try:
  if isinstance(v,bool) or str(int(v))!=str(v):raise ValueError()
  v=int(v)
 except (ValueError,TypeError):raise c.Problem('请填写有效的'+k)
 if not minimum<=v<=maximum:raise c.Problem(k+'超出范围')
 return v
def expiry(p):
 v=p.get('expires_at')
 if v in (None,''):return None
 if type(v) not in (int,float) or not time.time()<v<time.time()+20*366*86400:raise c.Problem('到期时间须在未来 20 年内')
 return v
def url(value):
 if not isinstance(value,str) or len(value)>2000:raise c.Problem('下载地址或回调地址过长')
 try:u=urlsplit(value);port=u.port
 except ValueError:raise c.Problem('地址格式不正确')
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment or port not in (None,443):raise c.Problem('请使用不含账号密码的 HTTPS 地址（443 端口）')
 if u.hostname.lower() in ('localhost','localhost.localdomain') or '.' not in u.hostname:raise c.Problem('请使用公网域名')
 try:
  if not ipaddress.ip_address(u.hostname).is_global:raise c.Problem('不允许使用内部网络地址')
 except ValueError:pass
 return value

def scope(db,user,customer_id):
 import android_fleet as fleet
 if customer_id and not fleet.visible(db,user,customer_id):raise c.Problem('没有该客户的使用权限',403)
def device(db,user,key):
 d=c.need(db,'android_devices',key);scope(db,user,d['customer_id'])
 if d['state']!='active':raise c.Problem('此设备已撤销')
 return d
def resource(db,key,kind=None):
 r=c.need(db,'android_resources',key)
 if kind and r['kind']!=kind:raise c.Problem('关联资料类型不匹配')
 r['data']=json.loads(r['data']);return r
def active(db,key,kind):
 r=resource(db,key,kind)
 if r['state']!='active':raise c.Problem('关联资料尚未启用')
 return r

def save(db,user,p):
 kind=p.get('kind')
 if kind not in KINDS:raise c.Problem('资料类型无效')
 state=p.get('state','active')
 if state not in ('draft','active','disabled'):raise c.Problem('状态无效')
 product=customer=dev=None;data={};previous=None;key=p.get('id')
 if key:
  previous=resource(db,key,kind);scope(db,user,previous['customer_id'])
  if type(p.get('revision')) is not int or p['revision']!=previous['revision']:raise c.Problem('资料已被修改，请更新页面后重试',409)
 if kind=='site':
  customer=c.need(db,'customers',p.get('customer_id'))['id'];scope(db,user,customer)
  data={'name':txt(p,'name','场地名称'),'address':txt(p,'address','地址',False,500),'contact':txt(p,'contact','联系人',False)}
 elif kind in ('feature','package','content'):
  product=c.need(db,'android_products',p.get('product_id'))['id'];data={'name':txt(p,'name','名称')}
  if kind=='feature':
   code=txt(p,'key','功能标识')
   if not __import__('re').fullmatch(r'[a-z][a-z0-9_.-]{0,63}',code):raise c.Problem('功能标识使用小写字母、数字、点或下划线')
   data['key']=code
  else:
   data.update(url=url(txt(p,'url','HTTPS 文件地址',limit=2000)),sha256=txt(p,'sha256','文件 SHA-256').lower(),size_bytes=integer(p,'size_bytes',1,2147483647),version=txt(p,'version','版本'))
   if not __import__('re').fullmatch('[a-f0-9]{64}',data['sha256']):raise c.Problem('SHA-256 应为 64 位十六进制')
   if kind=='package':
    cert=txt(p,'certificate_sha256','签名证书 SHA-256').lower()
    if not __import__('re').fullmatch('[a-f0-9]{64}',cert):raise c.Problem('签名证书 SHA-256 应为 64 位十六进制')
    file_name=txt(p,'file_name','原始 APK 文件名',False,255)
    if file_name and ('/' in file_name or '\\' in file_name or not file_name.lower().endswith('.apk')):raise c.Problem('请填写 APK 文件名，不要填写完整路径')
    data['file_name']=file_name
    data.update(version_code=integer(p,'version_code',1,2100000000),min_sdk=integer(p,'min_sdk',26,100),certificate_sha256=cert,package_name=c.need(db,'android_products',product)['package_name'],verification='待设备下载、文件校验和签名核验')
   else:
    if p.get('pricing','free') not in ('free','paid'):raise c.Problem('请选择免费或付费内容')
    data['pricing']=p.get('pricing','free')
 elif kind in ('entitlement','content_grant'):
  d=device(db,user,p.get('device_id'));dev=d['id'];customer=d['customer_id'];product=d['product_id'];ref=active(db,p.get('resource_id'),'feature' if kind=='entitlement' else 'content')
  if ref['product_id']!=product:raise c.Problem('授权内容与设备产品不一致')
  data={'resource_id':ref['id'],'expires_at':expiry(p)}
 elif kind=='alert_rule':
  if p.get('rule_type') not in ('offline','license_expiring'):raise c.Problem('告警类型无效')
  data={'name':txt(p,'name','规则名称'),'rule_type':p['rule_type'],'threshold':integer(p,'threshold',30 if p['rule_type']=='offline' else 1,10080 if p['rule_type']=='offline' else 365)}
 else:
  customer=p.get('customer_id') or None
  if customer:c.need(db,'customers',customer);scope(db,user,customer)
  events=p.get('events')
  if not isinstance(events,list) or not events or any(e not in EVENTS for e in events):raise c.Problem('请选择支持的回调事件')
  data={'name':txt(p,'name','回调名称'),'url':url(txt(p,'url','HTTPS 回调地址',limit=2000)),'events':list(dict.fromkeys(events)),'secret':previous['data']['secret'] if previous else secrets.token_urlsafe(32)}
 # Prevent silent reassignment of a referenced artifact, customer or device.
 if previous and (previous['product_id']!=product or previous['customer_id']!=customer or previous['device_id']!=dev):raise c.Problem('不能修改资料的产品、客户或设备归属，请新建资料')
 if kind=='feature':
  for row in db.execute("SELECT id,data FROM android_resources WHERE kind='feature' AND product_id=?",(product,)):
   if row['id']!=key and json.loads(row['data'])['key']==data['key']:raise c.Problem('该产品已有相同功能标识',409)
 if kind=='package':
  for row in db.execute("SELECT id,data FROM android_resources WHERE kind='package' AND product_id=?",(product,)):
   if row['id']!=key and json.loads(row['data'])['version_code']==data['version_code']:raise c.Problem('该产品已有相同 versionCode',409)
 if kind in ('entitlement','content_grant') and state=='active':
  for row in db.execute("SELECT id,data FROM android_resources WHERE kind=? AND device_id=? AND state='active'",(kind,dev)):
   if row['id']!=key and json.loads(row['data'])['resource_id']==data['resource_id']:raise c.Problem('设备已有此项有效授权，请修改原记录',409)
 stamp=c.now()
 if previous:db.execute('UPDATE android_resources SET data=?,state=?,revision=revision+1,updated_at=? WHERE id=?',(dump(data),state,stamp,key))
 else:
  key=c.uid();db.execute('INSERT INTO android_resources VALUES(?,?,?,?,?,?,?,1,?,?,?)',(key,kind,product,customer,dev,dump(data),state,user['id'],stamp,stamp))
 c.audit(db,user,'android_'+kind,key,'保存安卓业务资料',{'state':state})
 return {'ok':True,'id':key,**({'signing_secret':data['secret']} if kind=='webhook' and not previous else {})}

def change_state(db,user,p):
 r=resource(db,p.get('id'));scope(db,user,r['customer_id'])
 return save(db,user,{**r['data'],'kind':r['kind'],'product_id':r['product_id'],'customer_id':r['customer_id'],'device_id':r['device_id'],'id':r['id'],'revision':p.get('revision'),'state':p.get('state')})

def config(db,d):
 stamp=time.time();features=[];contents=[]
 all_resources=[resource(db,r['id']) for r in db.execute("SELECT id FROM android_resources WHERE product_id=? AND state='active'",(d['product_id'],))]
 refs={r['id']:r for r in all_resources};grants={}
 for r in all_resources:
  if r['device_id']==d['id'] and r['kind'] in ('entitlement','content_grant'):
   exp=r['data']['expires_at']
   if exp is None or exp>stamp:grants[r['data']['resource_id']]=exp
 for r in all_resources:
  if r['kind']=='feature' and r['id'] in grants:features.append({'key':r['data']['key'],'expires_at':grants[r['id']]})
  if r['kind']=='content' and (r['data']['pricing']=='free' or r['id'] in grants):contents.append({'id':r['id'],**r['data'],'expires_at':grants.get(r['id'])})
 payload={'schema_version':1,'device_id':d['id'],'product_id':d['product_id'],'features':features,'contents':contents,'offline_valid_until':min([stamp+86400]+[v for v in grants.values() if v]),'enforcement':'游戏端授权与内容执行接口待适配'}
 payload['revision']=hashlib.sha256(dump({'features':features,'contents':contents}).encode()).hexdigest()
 return payload

def emit(db,event,d,key,detail=None):
 # Only minimal scoped data enters partner callbacks, never device credentials or logs.
 for row in db.execute("SELECT * FROM android_resources WHERE kind='webhook' AND state='active'"):
  r=dict(row);settings=json.loads(r['data'])
  if (r['customer_id'] and r['customer_id']!=d['customer_id']) or event not in settings['events']:continue
  body=dump({'event':event,'event_id':key,'device_id':d['id'],'customer_id':d['customer_id'],'site':d['site'],'detail':detail or {},'created_at':c.now()})
  db.execute("INSERT OR IGNORE INTO android_deliveries(id,webhook_id,event_key,body,state,next_at,created_at) VALUES(?,?,?,?, 'pending',?,?)",(c.uid(),r['id'],key,body,time.time(),c.now()))

def task_create(db,user,p):
 d=device(db,user,p.get('device_id'));kind=p.get('task_type')
 if kind not in TASKS:raise c.Problem('任务类型无效')
 payload={'schema_version':1,'product_id':d['product_id']}
 if kind in ('install_apk','rollback_apk','sync_content'):
  ref=active(db,p.get('resource_id'),'content' if kind=='sync_content' else 'package')
  if ref['product_id']!=d['product_id']:raise c.Problem('任务文件与设备产品不一致')
  if kind=='sync_content' and ref['id'] not in {r['id'] for r in config(db,d)['contents']}:raise c.Problem('此设备没有该内容包权益')
  payload.update(resource_id=ref['id'],artifact=ref['data'],resource_revision=ref['revision'])
  if kind!='sync_content':
   current=json.loads(d['telemetry']);version=current.get('app_version_code')
   if kind=='install_apk' and version is not None and ref['data']['version_code']<=version:raise c.Problem('更新版本须高于当前版本；恢复旧版本请使用恢复任务')
   payload.update(recovery_policy='失败后保留失败记录，不自动降级；恢复任务需人工选择已验证旧包',previous_version=version)
 reason=txt(p,'note','任务说明',False,500);payload['note']=reason
 capabilities=json.loads(d['telemetry']).get('supported_tasks',[]);state='draft' if kind in capabilities else 'waiting_adapter';key=c.uid();stamp=c.now()
 db.execute('INSERT INTO android_tasks(id,device_id,kind,payload,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(key,d['id'],kind,dump(payload),state,user['id'],stamp,stamp));c.audit(db,user,'android_task',key,'创建安卓任务草稿',{'kind':kind,'state':state})
 return {'ok':True,'id':key,'state':state}

def task_action(db,user,p):
 t=c.need(db,'android_tasks',p.get('id'));d=device(db,user,t['device_id']);op=p.get('operation')
 if op=='cancel':
  if t['state']=='running':raise c.Problem('执行中的任务不能取消，须等待回执或超时')
  if t['state'] in ('succeeded','cancelled'):raise c.Problem('此任务已结束')
  db.execute("UPDATE android_tasks SET state='cancelled',updated_at=? WHERE id=?",(c.now(),t['id']))
 elif op in ('queue','retry'):
  if t['state'] not in ('draft','waiting_adapter','failed','unsupported'):raise c.Problem('此状态不能下发或重试')
  if t['kind'] not in json.loads(d['telemetry']).get('supported_tasks',[]):raise c.Problem('设备执行适配器尚未接入；任务保留在待接入状态')
  if t['attempts']>=t['max_attempts']:raise c.Problem('已达到 3 次尝试上限，请核对原因后新建任务')
  payload=json.loads(t['payload'])
  if payload.get('resource_id'):
   r=active(db,payload['resource_id'],'content' if t['kind']=='sync_content' else 'package')
   if r['revision']!=payload['resource_revision']:raise c.Problem('文件资料已修改，请新建任务，避免下发旧快照')
   if t['kind']=='sync_content' and r['id'] not in {v['id'] for v in config(db,d)['contents']}:raise c.Problem('设备内容权益已失效')
  db.execute("UPDATE android_tasks SET state='queued',lease_hash=NULL,lease_until=NULL,updated_at=? WHERE id=?",(c.now(),t['id']))
 else:raise c.Problem('任务操作无效')
 c.audit(db,user,'android_task',t['id'],'调整安卓任务',{'operation':op});return {'ok':True}

def authenticate(db,authorization):
 if not authorization.startswith('Bearer ') or not 43<=len(authorization[7:])<=100:raise c.Problem('设备凭证无效',401)
 d=c.row(db,"SELECT * FROM android_devices WHERE token_hash=? AND state='active'",(hashlib.sha256(authorization[7:].encode()).hexdigest(),))
 if not d:raise c.Problem('设备凭证失效或设备已撤销',401)
 return d

def ingest(db,d,events):
 if not isinstance(events,list) or len(events)>50:raise c.Problem('每批最多 50 条事件')
 prepared=[]
 for e in events:
  if not isinstance(e,dict) or not isinstance(e.get('event_id'),str) or not 1<=len(e['event_id'])<=100 or e.get('category') not in ('operation','diagnostic','game'):raise c.Problem('事件格式不正确')
  value=e.get('data')
  if not isinstance(value,dict) or len(dump(value).encode())>8192:raise c.Problem('单条事件需为不超过 8 KB 的对象')
  if e['category']=='diagnostic' and set(value)-{'message','agent_version','android_version','model','task_id','error'}:raise c.Problem('诊断仅接收指定字段，请勿上传凭证或完整设备私有数据')
  prepared.append((e,value))
 ack=[]
 for e,value in prepared:
  old=db.execute('SELECT data,category FROM android_events WHERE device_id=? AND event_id=?',(d['id'],e['event_id'])).fetchone()
  if old and (json.loads(old['data'])!=value or old['category']!=e['category']):raise c.Problem('同一事件编号的内容不能改变',409)
  if not old:
   db.execute('INSERT INTO android_events VALUES(?,?,?,?,?,?)',(c.uid(),d['id'],e['event_id'],e['category'],dump(value),c.now()))
   if e['category']=='game' and value.get('event')=='game.session_ended':emit(db,'game.session_ended',d,'game:'+d['id']+':'+e['event_id'],{'session_id':str(value.get('session_id',''))[:100]})
  ack.append(e['event_id'])
 return ack

def sync(db,p,authorization):
 import android_fleet as fleet
 d=authenticate(db,authorization);report=fleet.report(p)
 if report.get('package_name')!=c.need(db,'android_products',d['product_id'])['package_name']:raise c.Problem('上报产品不一致')
 if report.get('protocol_version')!=2:raise c.Problem('请更新管理 APK 至任务协议版本 2')
 d['telemetry']=dump(report);db.execute('UPDATE android_devices SET telemetry=?,last_seen=? WHERE id=?',(d['telemetry'],time.time(),d['id']))
 ack=ingest(db,d,p.get('events',[]));receipt=p.get('receipt');lease_response=None;receipt_status=None
 if receipt:
  if not isinstance(receipt,dict):raise c.Problem('任务回执格式无效')
  t=c.need(db,'android_tasks',receipt.get('task_id'))
  if t['device_id']!=d['id']:raise c.Problem('不能确认其他设备的任务',403)
  lease=receipt.get('lease','');state=receipt.get('state');result=receipt.get('result',{})
  valid_lease=isinstance(lease,str) and t['lease_hash'] and hmac.compare_digest(t['lease_hash'],hashlib.sha256(lease.encode()).hexdigest())
  if state not in ('succeeded','failed','unsupported') or not isinstance(result,dict) or len(dump(result).encode())>8192:raise c.Problem('任务结果格式无效')
  if not valid_lease:
   receipt_status='stale_lease'
  elif t['state'] in ('succeeded','failed','unsupported'):
   if t['state']!=state or json.loads(t['result'])!=result:raise c.Problem('已完成任务的结果不能改变',409)
  elif t['state']=='running' and t['lease_until']>=time.time():
   db.execute('UPDATE android_tasks SET state=?,result=?,updated_at=? WHERE id=?',(state,dump(result),c.now(),t['id']));emit(db,'task.succeeded' if state=='succeeded' else 'task.failed',d,'task:'+t['id']+':'+str(t['attempts']),{'task_id':t['id'],'kind':t['kind'],'state':state})
  else:receipt_status='expired_lease'
  lease_response=t['id']
 # A stable client request ID lets a lost response replay the same task lease.
 request_id=p.get('request_id')
 if not isinstance(request_id,str) or not 16<=len(request_id)<=100:raise c.Problem('同步请求编号无效')
 running=c.row(db,"SELECT * FROM android_tasks WHERE device_id=? AND state='running' ORDER BY created_at LIMIT 1",(d['id'],))
 job=None
 if not running:
  for raw in db.execute("SELECT * FROM android_tasks WHERE device_id=? AND state='queued' ORDER BY created_at,id",(d['id'],)):
   t=dict(raw)
   if t['kind'] not in report.get('supported_tasks',[]):
    db.execute("UPDATE android_tasks SET state='waiting_adapter',updated_at=? WHERE id=?",(c.now(),t['id']));continue
   payload=json.loads(t['payload'])
   if payload.get('resource_id'):
    try:
     r=active(db,payload['resource_id'],'content' if t['kind']=='sync_content' else 'package')
     if r['revision']!=payload['resource_revision']:raise c.Problem('文件资料已改变')
     if t['kind']=='sync_content' and r['id'] not in {v['id'] for v in config(db,d)['contents']}:raise c.Problem('内容权益已失效')
    except c.Problem as err:
     db.execute("UPDATE android_tasks SET state='failed',result=?,updated_at=? WHERE id=?",(dump({'error':err.message}),c.now(),t['id']))
     emit(db,'task.failed',d,'task:'+t['id']+':preflight',{'task_id':t['id'],'state':'failed'});continue
   # Deterministic per-attempt lease, derived from device credential + request ID.
   # Stored result remembers request_id so a lost sync response can replay it.
   lease=hmac.new(authorization[7:].encode(),(t['id']+':'+str(t['attempts']+1)+':'+request_id).encode(),hashlib.sha256).hexdigest()
   lease_until=time.time()+600
   db.execute("UPDATE android_tasks SET state='running',attempts=attempts+1,lease_hash=?,lease_until=?,result=?,updated_at=? WHERE id=?",(hashlib.sha256(lease.encode()).hexdigest(),lease_until,dump({'request_id':request_id}),c.now(),t['id']))
   job={'id':t['id'],'kind':t['kind'],'payload':json.loads(t['payload']),'lease':lease,'lease_until':lease_until};break
 elif json.loads(running['result']).get('request_id')==request_id and running['lease_until']>=time.time():
  lease=hmac.new(authorization[7:].encode(),(running['id']+':'+str(running['attempts'])+':'+request_id).encode(),hashlib.sha256).hexdigest();job={'id':running['id'],'kind':running['kind'],'payload':json.loads(running['payload']),'lease':lease,'lease_until':running['lease_until']}
 return {'ok':True,'acknowledged_events':ack,'acknowledged_task':lease_response,'receipt_status':receipt_status,'config':config(db,d),'task':job,'server_time':time.time()}

def maintenance(db):
 stamp=time.time()
 for raw in db.execute("SELECT * FROM android_tasks WHERE state='running' AND lease_until<?",(stamp,)):
  t=dict(raw);state='failed' if t['attempts']>=t['max_attempts'] else 'queued';db.execute('UPDATE android_tasks SET state=?,lease_hash=NULL,lease_until=NULL,result=?,updated_at=? WHERE id=?',(state,dump({'error':'设备执行超时，未收到确认；达到上限后需人工核对','outcome_unknown':True}),c.now(),t['id']))
  if state=='failed':emit(db,'task.failed',c.need(db,'android_devices',t['device_id']),'task:'+t['id']+':timeout',{'task_id':t['id'],'state':'failed','outcome_unknown':True})
 for raw in db.execute("SELECT * FROM android_resources WHERE kind='alert_rule' AND state='active'"):
  rule=dict(raw);params=json.loads(rule['data'])
  for row in db.execute("SELECT * FROM android_devices WHERE state='active'"):
   d=dict(row);trigger=False
   if params['rule_type']=='offline':trigger=bool(d['last_seen'] and stamp-d['last_seen']>params['threshold']*60);message='超过 '+str(params['threshold'])+' 分钟未收到设备上报，请核对网络及系统调度'
   else:
    exps=[json.loads(e['data']).get('expires_at') for e in db.execute("SELECT data FROM android_resources WHERE kind='entitlement' AND device_id=? AND state='active'",(d['id'],))];trigger=any(v and v<stamp+params['threshold']*86400 for v in exps);message='设备功能权益已到期或即将在 '+str(params['threshold'])+' 天内到期'
   existing=c.row(db,"SELECT * FROM android_alerts WHERE rule_id=? AND device_id=? AND state='open'",(rule['id'],d['id']))
   if trigger and not existing:
    key=c.uid();db.execute("INSERT INTO android_alerts VALUES(?,?,?,'open',?,?,NULL)",(key,rule['id'],d['id'],message,c.now()))
    if params['rule_type']=='offline':emit(db,'device.offline',d,'alert:'+key,{'message':message})
   elif not trigger and existing:
    db.execute("UPDATE android_alerts SET state='resolved',resolved_at=? WHERE id=?",(c.now(),existing['id']))
    if params['rule_type']=='offline':emit(db,'device.recovered',d,'recovered:'+existing['id'])
 # Revoked devices and disabled rules must not leave permanently open alerts.
 db.execute("UPDATE android_alerts SET state='resolved',resolved_at=? WHERE state='open' AND (device_id IN (SELECT id FROM android_devices WHERE state!='active') OR rule_id IN (SELECT id FROM android_resources WHERE state!='active'))",(c.now(),))
 db.execute("DELETE FROM android_events WHERE created_at < ?",(__import__('datetime').datetime.fromtimestamp(stamp-30*86400,__import__('datetime').timezone.utc).isoformat(),))

def snapshot(db,user,ids):
 resources=[]
 for raw in db.execute('SELECT * FROM android_resources ORDER BY created_at DESC,id'):
  r=dict(raw)
  if r['customer_id'] and r['customer_id'] not in ids:continue
  r['data']=json.loads(r['data']);r['data'].pop('secret',None);resources.append(r)
 visible_devices={r['id'] for r in db.execute('SELECT id,customer_id FROM android_devices') if r['customer_id'] in ids}
 def records(table):return [dict(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY created_at DESC LIMIT 500') if r['device_id'] in visible_devices]
 tasks=records('android_tasks')
 for t in tasks:
  t.pop('lease_hash',None);t['payload']=json.loads(t['payload']);t['result']=json.loads(t['result'])
 events=records('android_events')
 for e in events:e['data']=json.loads(e['data'])
 hook_ids={r['id'] for r in resources if r['kind']=='webhook'}
 deliveries=[{k:r[k] for k in ('id','webhook_id','state','attempts','next_at','last_result','created_at')} for r in db.execute('SELECT * FROM android_deliveries ORDER BY created_at DESC LIMIT 200') if r['webhook_id'] in hook_ids]
 return {'resources':resources,'tasks':tasks,'events':events,'alerts':records('android_alerts'),'deliveries':deliveries,'task_types':list(TASKS),'protocol_version':2,'deployment_baseline':{'board_model':'GB-RK3588','chipset':'RK3588','android_version':'12','sdk_int':31,'apk_naming':'YW_游戏名称_版本号_日期.apk'},'scheduler_last_run':float((c.row(db,"SELECT value FROM settings WHERE key='android_ops_last_run'") or {}).get('value',0))}

class PinnedHTTPS(http.client.HTTPSConnection):
 def __init__(self,host,address):
  super().__init__(host,timeout=10);self.address=address
 def connect(self):
  raw=socket.create_connection((self.address,443),timeout=10)
  try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
  except Exception:raw.close();raise

def send_delivery(settings,body,delivery_id):
 # Resolve and pin a public IP, retain hostname TLS verification, never follow redirects.
 u=urlsplit(url(settings['url']));addresses={a[4][0] for a in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
 if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('回调地址解析到内部网络，已阻止')
 stamp=str(int(time.time()));raw=body.encode();signature=hmac.new(settings['secret'].encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest();conn=PinnedHTTPS(u.hostname,sorted(addresses)[0])
 try:
  conn.request('POST',(u.path or '/')+('?' +u.query if u.query else ''),raw,{'Content-Type':'application/json','X-Yifun-Signature':'sha256='+signature,'X-Yifun-Timestamp':stamp,'X-Yifun-Delivery':delivery_id})
  response=conn.getresponse();status=response.status;response.read(4096)
  if not 200<=status<300:raise ValueError('HTTP '+str(status))
 finally:conn.close()
 return 'HTTP '+str(status)

def process_delivery():
 import database
 stamp=time.time()
 with database.connect() as db:
  raw=db.execute("SELECT * FROM android_deliveries WHERE (state IN ('pending','retry') AND next_at<=?) OR (state='sending' AND lease_until<?) ORDER BY next_at LIMIT 1",(stamp,stamp)).fetchone()
  if not raw:return
  delivery=dict(raw)
  if delivery['attempts']>=6:
   db.execute("UPDATE android_deliveries SET state='failed',last_result='发送中断且已达到尝试上限，须人工核对接收方记录' WHERE id=?",(delivery['id'],));return
  hook=resource(db,delivery['webhook_id'],'webhook')
  if hook['state']!='active':db.execute("UPDATE android_deliveries SET state='cancelled' WHERE id=?",(delivery['id'],));return
  lease=secrets.token_hex(16);db.execute("UPDATE android_deliveries SET state='sending',attempts=attempts+1,lease_hash=?,lease_until=? WHERE id=?",(lease,stamp+60,delivery['id']))
 try:message=send_delivery(hook['data'],delivery['body'],delivery['id']);state='delivered'
 except Exception as e:message=str(e)[:300];state='failed' if delivery['attempts']+1>=6 else 'retry'
 with database.connect() as db:db.execute('UPDATE android_deliveries SET state=?,last_result=?,next_at=?,lease_until=NULL WHERE id=? AND lease_hash=?',(state,message,time.time()+min(3600,30*(2**delivery['attempts'])),delivery['id'],lease))

def run_once():
 import database
 with database.connect() as db:
  maintenance(db)
  db.execute("INSERT INTO settings(key,value) VALUES('android_ops_last_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
 for _ in range(3):process_delivery()

def start():
 def loop():
  import database,logging
  while True:
   try:
    run_once()
   except Exception:logging.exception('Android operations maintenance failed')
   time.sleep(60)
 threading.Thread(target=loop,name='android-operations',daemon=True).start()
