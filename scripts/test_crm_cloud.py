import sys,sqlite3,json,os,unittest,copy,types
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import crm_cloud as c
class CRMTest(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
  self.snap={'schemaVersion':1,'projectionRevision':2,'source':'yifun-crm','admin_viewer_id':'admin','stage_labels':[['quoted','已报价']],'records':{'customers':[{'id':'one','name':'客户甲','market':'内贸','owner_id':'staff','grade':'A','created':'2026-09-01','acquired':'2026-11-02'},{'id':'two','name':'客户乙','market':'外贸','owner_id':'other','grade':'B','created':'2026-10-01','acquired':'2026-10-01'}],'projects':[{'project_id':'p1','name':'项目甲','lead_id':'one','owner_id':'staff','market':'内贸','stage':'quoted','stage_at':'2026-11-02'}],'quotes':[{'id':'q1','project_id':'p1','owner_id':'staff','created':'2026-11-02','summary':{'available':True,'currency':'CNY','amount_minor':12300}}],'deals':[{'id':'d1','lead_id':'one','owner_id':'staff','market':'内贸','deal_date':'2026-11-02','currency':'CNY','total_minor':10000},{'id':'d2','lead_id':'two','owner_id':'other','market':'外贸','deal_date':'2026-11-02','currency':'USD','total_minor':5000}],'orders':[]},'viewers':[{'id':'admin','allowed':True,'email':'boss@corp.test','markets':['内贸','外贸'],'people':[{'id':'staff','name':'业务甲','active':1},{'id':'other','name':'业务乙','active':1}],'customers':['one','two'],'projects':['p1'],'quotes':['q1'],'deals':['d1','d2'],'orders':[]},{'id':'staff','allowed':True,'personal':True,'email':'staff@corp.test','markets':['内贸'],'people':[{'id':'staff','name':'业务甲','active':1}],'customers':['one'],'projects':['p1'],'quotes':['q1'],'deals':['d1'],'orders':[]}]}
  self.admin={'role':'admin','email':'group-owner@corp.test'};self.staff={'role':'sales','email':'STAFF@corp.test'}
  c.save(self.db,{'snapshot':self.snap})
 def tearDown(self):self.db.close()
 def test_counts_original_dates_and_separate_currencies(self):
  c.validate(self.snap);r=c.view(self.db,self.admin,'2026-11-01','2026-11-30','内贸')
  self.assertEqual(r['summary']['total_customers'],1);self.assertEqual(r['summary']['customers'],1);self.assertEqual(r['summary']['quoted'],{'CNY':12300});self.assertEqual(r['summary']['won'],{'CNY':10000})
  self.assertEqual(c.view(self.db,self.admin,'2026-11-01','2026-11-30','全部')['summary']['won'],{'CNY':10000,'USD':5000})
  self.assertEqual(c.view(self.db,self.admin,'2026-10-01','2026-10-31','内贸')['summary']['customers'],0)
 def test_source_scopes_and_email_not_names(self):
  r=c.view(self.db,self.staff,'2026-11-01','2026-11-30','全部');self.assertEqual([x['id'] for x in r['all_customers']],['one'])
  with self.assertRaises(Exception):c.view(self.db,self.staff,'2026-11-01','2026-11-30','外贸')
  with self.assertRaises(Exception):c.selected_viewer(self.snap,{'role':'sales','name':'业务甲','email':'not-linked@corp.test'})
  broken=copy.deepcopy(self.snap);broken['viewers'][1]['customers'].append('missing')
  with self.assertRaises(ValueError):c.validate(broken)
 def test_refresh_replaces_and_retains_last_good_snapshot(self):
  @contextmanager
  def connection():yield self.db
  @contextmanager
  def response(*args,**kwargs):yield types.SimpleNamespace(read=lambda limit:json.dumps(self.snap).encode())
  with patch.dict(os.environ,{'YIFUN_CRM_SYNC':'1'}),patch.object(c.database,'connect',connection),patch.object(c,'slot',return_value='08'):
   with patch.object(c.urllib.request,'urlopen',response):c.refresh()
   with patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('duplicate')):c.refresh()
   old=c.read(self.db);old['attempt_epoch']=0;c.save(self.db,old)
   with patch.object(c,'slot',return_value='12'),patch.object(c.urllib.request,'urlopen',side_effect=OSError('offline')),self.assertLogs(level='ERROR'):c.refresh()
   self.assertEqual(c.read(self.db)['snapshot'],self.snap);self.assertTrue(c.read(self.db)['error'])
   old=c.read(self.db);old['attempt_epoch']=0;c.save(self.db,old);self.snap['records']['customers'][0]['name']='客户甲已更新'
   with patch.object(c,'slot',return_value='12'),patch.object(c.urllib.request,'urlopen',response):c.refresh()
   self.assertEqual(c.read(self.db)['snapshot']['records']['customers'][0]['name'],'客户甲已更新')
if __name__=='__main__':unittest.main()
