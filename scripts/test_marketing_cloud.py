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
  v={'source':'yifun-marketing','schemaVersion':1,'accounts':[{'id':'a','views':3}]}
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
if __name__=='__main__':unittest.main()
