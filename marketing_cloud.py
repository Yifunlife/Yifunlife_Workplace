"""Read-only cloud reporting mirror. Keep last good snapshot on failure."""
import json,os,time,threading,urllib.request,logging
import database,core
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
def slot():
 now=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
 for hour in (23,12,8):
  if now.hour>=hour:return now.date().isoformat()+f"T{hour:02d}:00"
 return (now.date()-timedelta(days=1)).isoformat()+"T23:00"
KEY='marketing_cloud_v1'
_lock=threading.Lock()
def read(db):
 r=db.execute('SELECT value FROM settings WHERE key=?',(KEY,)).fetchone()
 return json.loads(r['value']) if r else {}
def save(db,v):db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(KEY,json.dumps(v,ensure_ascii=False)))
def refresh():
 if os.getenv('YIFUN_MARKETING_SYNC')!='1' or not _lock.acquire(False):return
 try:
  with database.connect() as db:old=read(db)
  current_slot=slot()
  if (old.get('slot')==current_slot and old.get('snapshot',{}).get('accountLinksVersion')==1) or time.time()-old.get('attempt_epoch',0)<300:return
  try:
   with urllib.request.urlopen('http://marketing.yifun.internal/snapshot',timeout=25) as response:
    raw=response.read(2*1024*1024+1)
   if len(raw)>2*1024*1024:raise ValueError('snapshot too large')
   v=json.loads(raw)
   if v.get('source')!='yifun-marketing' or v.get('schemaVersion')!=1 or not isinstance(v.get('accounts'),list):raise ValueError('invalid snapshot')
   ids=[a['id'] for a in v['accounts']]
   if len(ids)!=len(set(ids)):raise ValueError('duplicate account')
   old={'snapshot':v,'last_success':core.now(),'slot':current_slot,'error':None}
  except Exception:
   logging.exception('Marketing cloud reporting sync failed')
   old['error']='运营同步暂未成功，保留上次成功数据'
  old['attempt_epoch']=time.time()
  with database.connect() as db:save(db,old)
 finally:_lock.release()
def status(db):return {**read(db),'enabled':os.getenv('YIFUN_MARKETING_SYNC')=='1'}

def account_report(db,start,end,today,currency='CNY'):
 s=status(db);source=s.get('snapshot',{}).get('accounts',[])
 accounts=[]
 def minor(v):return round(v*100) if isinstance(v,(int,float)) else None
 for row in db.execute('SELECT a.*,e.name owner FROM marketing_accounts a LEFT JOIN employees e ON e.id=a.owner_id ORDER BY CAST(a.id AS INTEGER)'):
  a=dict(row);linked=[v for v in source if v.get('group_account_id')==a['id']]
  creator=next((v for v in linked if v['kind']=='创作报表'),{})
  ads=[v for v in linked if v['kind']=='广告报表']
  def fee(period):
   values=[v.get('periods',{}).get(period) for v in ads]
   if currency!='CNY' or not values or any(not v or v.get('status')!='ok' or not isinstance(v.get('metrics',{}).get('fee'),(int,float)) for v in values):return None
   return sum(minor(v['metrics']['fee']) for v in values)
  selected=[v for v in ads if any(v.get('periods',{}).get(k,{}).get('start')==start and v.get('periods',{}).get(k,{}).get('end')==end for k in ('month','year','yesterday'))]
  # Current source exports fixed report periods; never pretend they cover arbitrary group filters.
  range_key=next((k for k in ('month','year','yesterday') if ads and all(v.get('periods',{}).get(k,{}).get('start')==start and v.get('periods',{}).get(k,{}).get('end')==end for v in ads)),None)
  if start==today[:7]+'-01' and end==today:range_key='month'
  g=creator.get('growth',{})
  a.update(fans=creator.get('fans'),month_gain=g.get('net_followers'),today_gain=None,yesterday_gain=g.get('yesterday_net'),month_posts=g.get('posts'),cost=fee(range_key) if range_key else None,sales=None,month_cost=fee('month'),month_sales=None,annual_ads=fee('year'),monthly_ads=fee('month'),ratio=None,source_ids=[v['id'] for v in linked],data_end=creator.get('data_end'),source_connected=bool(linked))
  a['owner']=None  # A source-to-group employee mapping must be explicitly confirmed.
  accounts.append(a)
 markets=[]
 for market in ('内贸','外贸'):
  aa=[a for a in accounts if a['market']==market];m={'market':market,'account_count':len(aa),'connected_count':sum(a['source_connected'] for a in aa),'month_ratio':None}
  for key in ('cost','sales','month_cost','month_sales','annual_ads','monthly_ads','month_posts'):
   values=[a[key] for a in aa if a[key] is not None];m[key]=sum(values) if values else None
  markets.append(m)
 return {'shared_department_data':False,'test_mode':False,'currency':currency,'period':{'from':start,'to':end,'timezone':'Asia/Shanghai'},'today':today,'accounts':accounts,'markets':markets,'unassigned_spend_count':0,'cloud_sync':s,'unmapped_source_count':sum(not a.get('group_account_id') for a in source)}
