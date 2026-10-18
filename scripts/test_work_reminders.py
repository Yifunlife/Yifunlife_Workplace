import os,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
temp=tempfile.TemporaryDirectory()
os.environ.update(YIFUN_DATA_ROOT=temp.name,YIFUN_DEMO_MODE='1',YIFUN_DATABASE_BACKEND='local')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database,workplace,core,demo_data,work_reminders

class RemindersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workplace.init()
        with database.connect() as db:
            cls.admin=workplace.add_employee(db,dict(email='admin@qa.invalid',name='同名员工',password='qa-password-0000'),True)
            demo_data.seed(db,cls.admin)
            cls.sales=workplace.add_employee(db,dict(email='sales@qa.invalid',name='同名员工',password='qa-password-0000',role='sales'))
            cls.engineer=workplace.add_employee(db,dict(email='eng@qa.invalid',name='工程员工',password='qa-password-0000',role='engineering'))
            cls.ceo=workplace.add_employee(db,dict(email='ceo@qa.invalid',name='CEO',password='qa-password-0000',role='ceo'))
            cls.supplier=workplace.add_employee(db,dict(email='supplier@qa.invalid',name='供应商',password='qa-password-0000',role='supplier',supplier_id='DEMO-SUPPLIER-1'))
            for u in (cls.sales,cls.engineer):
                db.execute('INSERT INTO project_members VALUES(?,?,?,?,?)',('DEMO-PROJECT-1',u['id'],'member',cls.admin['id'],core.now()))
    def setUp(self):
        self.db=database.connect();self.db.execute('BEGIN')
    def tearDown(self):self.db.rollback();self.db.close()
    def report(self,u=None,**kw):return work_reminders.report(self.db,u or self.admin,today='2026-10-18',**kw)
    def task(self,id,owner,due='2026-10-18',status='planned',pid='DEMO-PROJECT-1'):
        demo_data.insert(self.db,'work_tasks',dict(id=id,project_id=pid,kind='task',title='任务 '+id,owner_id=owner,due_date=due,status=status,created_by=self.admin['id'],created_at=core.now(),updated_at=core.now()))
    def test_personal_uses_account_not_name(self):
        self.task('qa-personal',self.sales['id']);self.task('qa-admin',self.admin['id'])
        r=self.report(self.sales)
        self.assertIn('task:qa-personal',{i['id'] for i in r['items']})
        self.assertNotIn('task:qa-admin',{i['id'] for i in r['items']})
        self.assertNotIn('service:DEMO-SERVICE-001',{i['id'] for i in r['items']})
    def test_priority_and_completed_disappear(self):
        self.task('qa-late',self.sales['id'],'2026-10-17');self.task('qa-today',self.sales['id'])
        self.task('qa-soon',self.sales['id'],'2026-10-21');self.task('qa-done',self.sales['id'],status='done')
        rows=[i for i in self.report(self.sales)['items'] if i['source']=='task']
        self.assertEqual([i['urgency'] for i in rows],['overdue','today','soon'])
        self.db.execute("UPDATE work_tasks SET status='done' WHERE id='qa-late'")
        self.assertNotIn('task:qa-late',{i['id'] for i in self.report(self.sales)['items']})
    def test_project_and_center_scopes(self):
        self.task('qa-engineer',self.engineer['id'])
        self.assertIn('task:qa-engineer',{i['id'] for i in self.report(self.engineer,center='factory')['items']})
        self.assertNotIn('task:qa-engineer',{i['id'] for i in self.report(self.engineer,center='stock')['items']})
        with self.assertRaises(core.Problem):self.report(self.sales,project='DEMO-PROJECT-2')
        with self.assertRaises(core.Problem):self.report(self.sales,center='factory')
    def test_handoff_transfers_to_engineer(self):
        self.db.execute("UPDATE design_tasks SET status='handoff',owner_id=? WHERE id='DEMO-DESIGN-1'",(self.sales['id'],))
        self.assertNotIn('design:DEMO-DESIGN-1',{i['id'] for i in self.report(self.sales)['items']})
        self.assertIn('design:DEMO-DESIGN-1',{i['id'] for i in self.report(self.engineer,center='engineering')['items']})
        self.db.execute("UPDATE design_tasks SET status='accepted' WHERE id='DEMO-DESIGN-1'")
        self.assertNotIn('design:DEMO-DESIGN-1',{i['id'] for i in self.report(self.engineer)['items']})
    def test_privacy_and_supplier(self):
        self.task('qa-hidden',self.admin['id'],'2026-10-01',pid='DEMO-PROJECT-2')
        result=self.report(self.sales,center='crm')
        self.assertNotIn('task:qa-hidden',{i['id'] for i in result['items']+result['attention']})
        supplier=self.report(self.supplier,center='procurement')
        self.assertGreater(len(supplier['items']),0)
        self.assertTrue(all(i['source']=='purchase' for i in supplier['items']+supplier['attention']))
        self.assertTrue(all(not i['project_name'] for i in supplier['items']))
    def quote(self,key='qa-quote',final=False):
        snapshot=json.dumps({'workspaceProjectId':'DEMO-PROJECT-1'})
        demo_data.insert(self.db,'quotation_history',dict(id=key,contract_no=key,project_name='QA',created_by=self.sales['email'],snapshot_json=snapshot,generated_at=core.now(),lineage_id=key,is_finalized=int(final),final_amount=100 if final else None,final_currency='CNY' if final else None,project_id='DEMO-PROJECT-1'))
    def test_ceo_approval_and_completion(self):
        self.quote(final=True)
        demo_data.insert(self.db,'order_baselines',dict(id='qa-order',number='QA-ORDER',project_id='DEMO-PROJECT-1',quote_id='qa-quote',kind='original',currency='CNY',agreed_minor=10000,raw_snapshot='{}',created_by=self.admin['id'],created_at=core.now()))
        demo_data.insert(self.db,'release_requests',dict(id='qa-release',baseline_id='qa-order',reason='QA放行',requested_by=self.admin['id'],created_at=core.now()))
        self.assertIn('release:qa-release',{i['id'] for i in self.report(self.ceo)['items']})
        self.assertNotIn('release:qa-release',{i['id'] for i in self.report(self.admin)['items']})
        self.assertIn('release:qa-release',{i['id'] for i in self.report(self.admin)['attention']})
        self.db.execute("UPDATE release_requests SET status='approved' WHERE id='qa-release'")
        self.assertNotIn('release:qa-release',{i['id'] for i in self.report(self.ceo)['items']})
    def test_quote_latest_revision_and_email_identity(self):
        self.quote('qa-old');self.quote('qa-new')
        rows=[i for i in self.report(self.sales,center='quote')['items'] if i['source']=='quote']
        self.assertEqual([i['id'] for i in rows],['quote:qa-new'])
        self.assertFalse(any(i['source']=='quote' for i in self.report(self.admin)['items']))
    def test_latest_followup_date(self):
        self.db.execute("UPDATE crm_leads SET owner_id=?,next_date='2026-10-01' WHERE id='DEMO-LEAD-1'",(self.sales['id'],))
        self.db.execute('INSERT INTO crm_followups VALUES(?,?,?,?,?,?,?,?,?)',('qa-follow','leads','DEMO-LEAD-1','2026-10-18','联系完成','明天回访','2026-10-19',self.sales['id'],core.now()))
        row=next(i for i in self.report(self.sales)['items'] if i['id']=='leads:DEMO-LEAD-1')
        self.assertEqual(row['due_date'],'2026-10-19');self.assertEqual(row['urgency'],'soon')
    def test_shanghai_date_boundary(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,10,18,16,5,tzinfo=timezone.utc).astimezone(tz)
        with patch.object(work_reminders,'datetime',Clock):
            self.assertEqual(work_reminders.report(self.db,self.admin)['today'],'2026-10-19')

if __name__=='__main__':unittest.main()
