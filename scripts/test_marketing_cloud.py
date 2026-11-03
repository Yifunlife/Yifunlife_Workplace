import sys,sqlite3,json,os,unittest,contextlib,types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import marketing_cloud as m
class Test(unittest.TestCase):
 def test_sync(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
  @contextlib.contextmanager
  def connect():yield db
  v={'source':'yifun-marketing','schemaVersion':1,'accountLinksVersion':1,'accounts':[{'id':'a','views':3}]}
  @contextlib.contextmanager
  def response(*a,**k):yield types.SimpleNamespace(read=lambda n:json.dumps(v).encode())
  with patch.dict(os.environ,{'YIFUN_MARKETING_SYNC':'1'}),patch.object(m.database,'connect',connect):
   with patch.object(m,'slot',return_value='08'),patch.object(m.urllib.request,'urlopen',response):m.refresh()
   self.assertEqual(m.read(db)['snapshot'],v)
   old=m.read(db);old['attempt_epoch']=0;m.save(db,old)
   with patch.object(m,'slot',return_value='12'),patch.object(m.urllib.request,'urlopen',side_effect=OSError('offline')):m.refresh()
   self.assertEqual(m.read(db)['snapshot'],v);self.assertTrue(m.read(db)['error'])
   old=m.read(db);old['attempt_epoch']=0;m.save(db,old);v['accounts'][0]['views']=9
   with patch.object(m,'slot',return_value='12'),patch.object(m.urllib.request,'urlopen',response):m.refresh()
   self.assertEqual(m.read(db)['snapshot']['accounts'][0]['views'],9)
   with patch.object(m,'slot',return_value='12'),patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('duplicate')):m.refresh()
 def test_shared_account_report(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE employees(id TEXT,name TEXT);CREATE TABLE marketing_accounts(id TEXT,market TEXT,platform TEXT,name TEXT,owner_id TEXT);INSERT INTO marketing_accounts VALUES('9','内贸','小红书','玩具号',NULL);")
  m.save(db,{'snapshot':{'accounts':[{'id':'creator','group_account_id':'9','kind':'创作报表','fans':7507,'growth':{'net_followers':6,'posts':1}},{'id':'ad','group_account_id':'9','kind':'广告报表','periods':{'month':{'status':'ok','start':'2026-11-01','end':'2026-11-02','metrics':{'fee':172.88}},'year':{'status':'ok','metrics':{'fee':1000}}}}]}})
  r=m.account_report(db,'2026-11-01','2026-11-03','2026-11-03')
  self.assertFalse(r['test_mode']);self.assertEqual(r['accounts'][0]['cost'],17288);self.assertEqual(r['accounts'][0]['fans'],7507);self.assertIsNone(r['accounts'][0]['sales']);self.assertEqual(r['markets'][0]['monthly_ads'],17288)
  current=m.read(db);current['snapshot']['accounts'].append({'id':'agency','kind':'广告报表','periods':{'year':{'status':'ok','metrics':{'fee':2000}}}});m.save(db,current)
  merged=m.account_report(db,'2026-11-01','2026-11-03','2026-11-03');self.assertEqual(merged['markets'][0]['annual_ads'],300000);self.assertEqual(merged['accounts'][0]['annual_ads'],100000);self.assertEqual(merged['unmapped_source_count'],1)
  self.assertIsNone(m.account_report(db,'2026-10-01','2026-11-03','2026-11-03')['accounts'][0]['cost'])
if __name__=='__main__':unittest.main()

