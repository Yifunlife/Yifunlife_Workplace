import os,sys,tempfile,json,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
root=tempfile.TemporaryDirectory();os.environ.update(YIFUN_DATA_ROOT=root.name,YIFUN_DATABASE_BACKEND='local',YIFUN_DEMO_MODE='0')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database,workplace,core,aftersales_cloud as cloud,project_access,aftercare,ceo_dashboard
class CloudSyncTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  workplace.init()
  with database.connect() as db:cls.owner=workplace.add_employee(db,dict(email='sync-qa@example.invalid',name='QA',password='local-sync-password'),True)
 def setUp(self):
  self.db=database.connect();self.db.execute('BEGIN')
  self.snapshot={'schemaVersion':1,'source':cloud.SOURCE,'customers':[{'id':'customer-1','company':'真实客户','country':'中国'}],
   'stores':[{'id':'store-1','customer_id':'customer-1','name':'门店一'}],
   'requests':[{'id':'request-1','customer_id':'customer-1','store_id':'store-1','status':'in_review','submitted_at':1792656000000},{'id':'pending','customer_id':'customer-1','store_id':'store-1','status':'pending','submitted_at':1792656000000}],
   'items':[{'id':'work-1','request_id':'request-1','version':1,'updated_at':1792656000000,'payload':{'product':'测试设备','issue':'故障一','stage':'审核','planned':'2026-10-22','owner':'专员'}}]}
 def tearDown(self):self.db.rollback();self.db.close()
 def apply(self):return cloud.apply_snapshot(self.db,self.snapshot,self.owner['id'])
 def test_idempotent_and_changes(self):
  self.assertEqual(self.apply(),{'items':1,'pending_requests':1,'changed':1});self.assertEqual(self.apply()['changed'],0)
  item=self.snapshot['items'][0];item.update(version=2,updated_at=1792742400000);item['payload'].update(stage='采购',issue='故障已确认');self.assertEqual(self.apply()['changed'],1)
  row=self.db.execute('SELECT * FROM service_tickets').fetchone();p=json.loads(row['payload']);self.assertEqual(p['stage'],'生产采购');self.assertEqual(p['description'],'故障已确认');self.assertEqual(row['version'],2)
  item.update(version=1);item['payload']['issue']='旧数据';self.assertEqual(self.apply()['changed'],0)
  item.update(version=3);item['payload']['stage']='已关闭';self.apply();self.assertEqual(json.loads(self.db.execute('SELECT payload FROM service_tickets').fetchone()[0])['stage'],'关闭与复盘')
 def test_invalid_snapshot_is_rejected_before_writes(self):
  self.snapshot['items'][0]['request_id']='missing'
  with self.assertRaises(ValueError):self.apply()
  self.assertEqual(self.db.execute('SELECT count(*) FROM service_tickets').fetchone()[0],0)
 def test_removed_source_is_retained_and_not_counted(self):
  self.apply();self.snapshot['items']=[];self.apply();r=self.db.execute('SELECT * FROM service_tickets').fetchone();self.assertTrue(json.loads(r['payload'])['sourceRemoved'])
  self.assertEqual(ceo_dashboard.dashboard(self.db,self.owner)['tickets'],[])
 def test_private_mirror_is_not_copied_into_editable_legacy_workflow(self):
  self.apply();aftercare.seed_legacy(self.db);self.assertEqual(self.db.execute('SELECT count(*) FROM af2_customer_work_items').fetchone()[0],0)
  self.assertEqual(len(ceo_dashboard.dashboard(self.db,self.owner)['tickets']),1)
 def test_names_do_not_link_unrelated_projects_or_grant_permissions(self):
  self.apply();pid=cloud.stable('project','store-1');self.assertFalse(project_access.visible_project(self.db,{'id':'outsider','role':'sales'},pid))
  self.assertEqual(self.db.execute('SELECT count(*) FROM project_members').fetchone()[0],0)
 def test_refresh_runs_once_per_slot_and_keeps_data_on_failure(self):
  from unittest.mock import patch
  from contextlib import contextmanager
  @contextmanager
  def connection():yield self.db
  class Reply:
   headers={'ETag':'"revision-1"'}
   def __enter__(r):return r
   def __exit__(r,*args):pass
   def read(r,limit):return json.dumps(self.snapshot).encode()
  at=datetime.fromisoformat('2026-10-23T00:00:00+00:00')
  with patch.dict(os.environ,{'YIFUN_AFTERSALES_SYNC':'1'}),patch.object(database,'connect',connection),patch.object(cloud.urllib.request,'urlopen',return_value=Reply()) as fetch:
   cloud.refresh(at=at);self.assertEqual(fetch.call_count,1);cloud.refresh(at=at);self.assertEqual(fetch.call_count,1)
   cloud.refresh(manual=True,at=at);self.assertEqual(fetch.call_count,2)
   before=self.db.execute('SELECT payload FROM service_tickets').fetchone()[0]
   fetch.side_effect=OSError('source unavailable')
   with self.assertLogs(level='ERROR'):cloud.refresh(at=datetime.fromisoformat('2026-10-23T10:00:00+00:00'))
   self.assertEqual(self.db.execute('SELECT payload FROM service_tickets').fetchone()[0],before)
   self.assertTrue(cloud.read_status(self.db)['error']);self.assertEqual(cloud.read_status(self.db)['slot'],'2026-10-23T08:00')
 def test_shanghai_schedule(self):
  for stamp,expected in [('2026-10-22T23:59:00+00:00','2026-10-22T18:00'),('2026-10-23T00:00:00+00:00','2026-10-23T08:00'),('2026-10-23T09:59:00+00:00','2026-10-23T08:00'),('2026-10-23T10:00:00+00:00','2026-10-23T18:00')]:self.assertEqual(cloud.slot(datetime.fromisoformat(stamp)),expected)
if __name__=='__main__':unittest.main()
