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
  if old.get('slot')==current_slot or time.time()-old.get('attempt_epoch',0)<300:return
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
