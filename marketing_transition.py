"""Reversibly archive only proven original marketing fixtures."""
import json,os
from datetime import datetime,timedelta
import core
from zoneinfo import ZoneInfo
KEY='marketing_real_data_transition_v1'
def run(db):
 if os.getenv('YIFUN_MARKETING_SYNC')!='1' or db.execute('SELECT 1 FROM settings WHERE key=?',(KEY,)).fetchone():return
 db.execute('CREATE TABLE IF NOT EXISTS marketing_demo_archive(table_name TEXT NOT NULL,record_key TEXT NOT NULL,payload TEXT NOT NULL,archived_at TEXT NOT NULL,PRIMARY KEY(table_name,record_key))')
 def archive(table,key,row):db.execute('INSERT OR IGNORE INTO marketing_demo_archive VALUES(?,?,?,?)',(table,key,json.dumps(dict(row),ensure_ascii=False),core.now()))
 for table in ('marketing_spends','marketing_test_contracts'):
  for row in db.execute('SELECT * FROM '+table+" WHERE id GLOB 'DEMO-*'").fetchall():
   archive(table,row['id'],row)
   db.execute('UPDATE '+table+" SET status='void' WHERE id=?",(row['id'],))
 marker=db.execute("SELECT value FROM settings WHERE key='shared_demo_seed_v1'").fetchone()
 if marker:
  day=datetime.fromisoformat(marker['value']).astimezone(ZoneInfo('Asia/Shanghai')).date();month=day.replace(day=1);previous=month-timedelta(days=1)
  for row in db.execute('SELECT * FROM marketing_daily').fetchall():
   try:i=int(row['account_id']);date=datetime.fromisoformat(row['day']).date()
   except (ValueError,TypeError):continue
   if not 1<=i<=18 or row['version']!=1:continue
   expected=(date==previous and row['fans']==i*1000 and row['posts']==0) or (month<=date<=day and row['fans']==i*1000+date.day*(i+7) and row['posts']==(1 if i%3 else 2))
   if expected:
    archive('marketing_daily',row['account_id']+':'+row['day'],row)
    db.execute('DELETE FROM marketing_daily WHERE account_id=? AND day=?',(row['account_id'],row['day']))
 db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(KEY,core.now()))
