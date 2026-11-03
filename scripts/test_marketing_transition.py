import sys,sqlite3,json,os,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import marketing_transition as m
class Test(unittest.TestCase):
 def test_archive_only_proven_fixtures(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);INSERT INTO settings VALUES('shared_demo_seed_v1','2026-10-11T02:00:00+00:00');CREATE TABLE marketing_spends(id TEXT,status TEXT);INSERT INTO marketing_spends VALUES('DEMO-SPEND-1','active'),('real-1','active');CREATE TABLE marketing_test_contracts(id TEXT,status TEXT);INSERT INTO marketing_test_contracts VALUES('DEMO-CONTRACT-1','active');CREATE TABLE marketing_daily(account_id TEXT,day TEXT,fans INTEGER,posts INTEGER,version INTEGER);INSERT INTO marketing_daily VALUES('1','2026-10-01',1008,1,1),('1','2026-10-02',5000,2,2);")
  with patch.dict(os.environ,{'YIFUN_MARKETING_SYNC':'1'}):m.run(db);m.run(db)
  self.assertEqual(db.execute('SELECT COUNT(*) FROM marketing_demo_archive').fetchone()[0],3)
  self.assertEqual(db.execute("SELECT status FROM marketing_spends WHERE id='real-1'").fetchone()[0],'active')
  self.assertEqual(db.execute('SELECT fans FROM marketing_daily').fetchone()[0],5000)
  self.assertEqual(json.loads(db.execute("SELECT payload FROM marketing_demo_archive WHERE table_name='marketing_spends'").fetchone()[0])['status'],'active')
if __name__=='__main__':unittest.main()
