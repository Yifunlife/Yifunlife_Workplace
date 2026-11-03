"""Private, read-only CRM mirror shared by authorized group dashboards."""
import json,os,time,threading,logging,urllib.request
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import database,core
KEY='crm_cloud_reporting_v1'
_lock=threading.Lock()
def slot(at=None):
 now=(at or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Shanghai'))
 for hour in (23,12,8):
  if now.hour>=hour:return now.date().isoformat()+f'T{hour:02d}:00'
 return (now.date()-timedelta(days=1)).isoformat()+'T23:00'
def read(db):
 r=db.execute('SELECT value FROM settings WHERE key=?',(KEY,)).fetchone()
 return json.loads(r['value']) if r else {}
def save(db,value):db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(KEY,json.dumps(value,ensure_ascii=False)))
def status(db):
 s=read(db)
 return {k:v for k,v in {**s,'enabled':os.getenv('YIFUN_CRM_SYNC')=='1','schedule':['08:00','12:00','23:00'],'timezone':'Asia/Shanghai'}.items() if k!='snapshot'}
def validate(v):
 if v.get('schemaVersion')!=1 or v.get('source')!='yifun-crm' or not isinstance(v.get('viewers'),list):raise ValueError('Invalid CRM projection')
 tables={}
 for key,field in [('customers','id'),('projects','project_id'),('quotes','id'),('deals','id'),('orders','id')]:
  rows=v.get('records',{}).get(key)
  if not isinstance(rows,list) or len(rows)>100000:raise ValueError('Invalid CRM records')
  ids=[r.get(field) for r in rows if isinstance(r,dict)]
  if len(ids)!=len(rows) or any(not isinstance(k,str) or not k for k in ids) or len(set(ids))!=len(ids):raise ValueError('Invalid CRM identity')
  tables[key]=set(ids)
 seen=set()
 for person in v['viewers']:
  if not isinstance(person,dict) or not isinstance(person.get('id'),str) or person['id'] in seen:raise ValueError('Invalid CRM viewer')
  seen.add(person['id'])
  if not person.get('allowed'):continue
  for key,allowed in tables.items():
   ids=person.get(key)
   if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(k not in allowed for k in ids):raise ValueError('Invalid CRM scope')
 if v.get('admin_viewer_id') not in seen:raise ValueError('Missing CRM administrator projection')
def refresh():
 if os.getenv('YIFUN_CRM_SYNC')!='1' or not _lock.acquire(False):return
 try:
  with database.connect() as db:previous=read(db)
  current_slot=slot()
  if (previous.get('slot')==current_slot and previous.get('snapshot',{}).get('projectionRevision')==2) or (previous.get('snapshot',{}).get('projectionRevision')==2 and time.time()-previous.get('attempt_epoch',0)<300):return
  try:
   with urllib.request.urlopen('http://crm.yifun.internal/snapshot',timeout=90) as response:raw=response.read(16*1024*1024+1)
   if len(raw)>16*1024*1024:raise ValueError('CRM projection too large')
   v=json.loads(raw);validate(v)
   previous={'snapshot':v,'last_success':core.now(),'slot':current_slot,'error':None,'viewer_count':len(v['viewers'])}
  except Exception:
   logging.exception('CRM synchronization failed')
   previous['error']='CRM同步暂未成功，保留上次成功数据。'
  previous['attempt_epoch']=time.time()
  with database.connect() as db:save(db,previous)
 finally:_lock.release()
def selected_viewer(snapshot,user):
 viewers=snapshot.get('viewers',[])
 if user['role'] in ('admin','ceo'):
  person=next((v for v in viewers if v['id']==snapshot.get('admin_viewer_id')),None)
 else:
  email=(user['email'] or '').strip().lower()
  matches=[v for v in viewers if email and (v.get('email') or '').strip().lower()==email]
  person=matches[0] if len(matches)==1 else None
 if not person or not person.get('allowed'):raise core.Problem('此集团账号尚未关联有权限的CRM账号，请核对双方账号邮箱。',403)
 expanded=dict(person)
 for key,field in [('customers','id'),('projects','project_id'),('quotes','id'),('deals','id'),('orders','id')]:
  table={r[field]:r for r in snapshot['records'][key]}
  expanded[key]=[table[k] for k in person[key]]
 return expanded
def view(db,user,start,end,market=None):
 state=read(db);snap=state.get('snapshot')
 if not snap:return {'sync':status(db),'ready':False,'period':{'from':start,'to':end}}
 person=selected_viewer(snap,user)
 allowed=list(person.get('markets') or [])
 if user['role'] in ('admin','ceo'):allowed+=['待确认']
 market=market or (allowed[0] if allowed else '内贸')
 if market not in allowed and market!='全部':raise core.Problem('没有此市场的数据权限。',403)
 def scoped(rows):return [r for r in rows if market=='全部' or r.get('market')==market]
 customers=scoped(person['customers']);projects=scoped(person['projects']);deals=scoped(person['deals']);quotes=person['quotes'];orders=scoped(person['orders'])
 def in_range(value):return bool(value and start<=str(value)[:10]<=end)
 acquired=[r for r in customers if in_range(r.get('acquired'))]
 project_ids={r['project_id'] for r in projects}
 quotes=[r for r in quotes if r['project_id'] in project_ids and in_range(r.get('created'))]
 selected_deals=[r for r in deals if in_range(r.get('deal_date'))]
 def amounts(rows,key):
  out={}
  for row in rows:
   value=row.get(key);currency=row.get('currency')
   expected='CNY' if row.get('market',market)=='内贸' else 'USD' if row.get('market',market)=='外贸' else None
   if isinstance(value,int) and currency and (expected is None or expected==currency):out[currency]=out.get(currency,0)+value
  return out
 stage_labels=dict(snap.get('stage_labels') or [])
 def summary(owner=None):
  cs=[r for r in customers if owner is None or r.get('owner_id')==owner]
  new=[r for r in acquired if owner is None or r.get('owner_id')==owner]
  ps=[r for r in projects if owner is None or r.get('owner_id')==owner]
  ds=[r for r in selected_deals if owner is None or r.get('owner_id')==owner]
  qs=[r for r in quotes if owner is None or r.get('owner_id')==owner]
  quoted=[{**r.get('summary',{}),'market':next((p.get('market') for p in projects if p['project_id']==r['project_id']),market)} for r in qs]
  return {'total_customers':len(cs),'customers':len(new),'grades':{g:sum(r.get('grade')==g for r in new) for g in ('VIP','A','B','C')},'total_grades':{g:sum(r.get('grade')==g for r in cs) for g in ('VIP','A','B','C')},'quoting_count':sum(p.get('stage') in ('design','quoted','negotiation') and in_range(p.get('stage_at')) for p in ps),'quoted':amounts(quoted,'amount_minor'),'deal_count':len(ds),'won':amounts(ds,'total_minor'),'unpriced':sum(d.get('total_minor') is None for d in ds)}
 people=[{**p,**summary(p['id'])} for p in person.get('people',[]) if any(r.get('owner_id')==p['id'] for r in customers+deals+projects)]
 return {'ready':True,'sync':status(db),'period':{'from':start,'to':end},'market':market,'markets':allowed,'personal':person.get('personal',False),'summary':summary(),'people':people,'customers':acquired,'all_customers':customers,'projects':projects,'deals':selected_deals,'orders':orders,'stage_labels':stage_labels,'source_url':'https://yifun-crm.yifunlife.workers.dev'}
