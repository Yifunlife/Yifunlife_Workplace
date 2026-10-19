import os,sys,tempfile,unittest,json,sqlite3
from pathlib import Path
temp=tempfile.TemporaryDirectory()
os.environ.update(YIFUN_DATA_ROOT=temp.name,YIFUN_DEMO_MODE='1',YIFUN_DATABASE_BACKEND='local')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workplace,database,demo_data,core,aftersales_expenses as costs,ceo_dashboard

class CostTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  workplace.init()
  with database.connect() as db:
   cls.owner=workplace.add_employee(db,dict(email='qa-cost@example.invalid',name='QA',password='local-cost-password'),True)
   demo_data.seed(db,cls.owner)
   cls.sales=workplace.add_employee(db,dict(email='qa-sales@example.invalid',name='商务',password='local-sales-password',role='sales'))
   cls.after=workplace.add_employee(db,dict(email='qa-after@example.invalid',name='售后',password='local-after-password',role='aftersales'))
 @classmethod
 def tearDownClass(cls):temp.cleanup()
 def setUp(self):
  self.db=database.connect();self.db.execute('BEGIN')
  self.projects={r['id']:dict(r) for r in self.db.execute('SELECT * FROM projects')}
 def tearDown(self):self.db.rollback();self.db.close()
 def save(self,ref='QA-COST',**extra):
  p=dict(ticket_id='DEMO-SERVICE-001',category='freight',amount='123.45',currency='CNY',record_date='2026-10-19',reference=ref,note='公司实际承担')
  p.update(extra);return costs.save(self.db,self.owner,p)
 def report(self,**kw):return costs.report(self.db,kw.get('projects',self.projects),kw.get('end','2026-10-19'))
 def test_year_month_currency_and_cutoff(self):
  self.save('JAN',amount='10',record_date='2026-01-01');self.save('OCT',currency='USD',amount='3.33');self.save('LAST',record_date='2025-12-31')
  r=self.report();self.assertEqual(r['annual'],[{'currency':'CNY','minor':1000},{'currency':'USD','minor':333}]);self.assertEqual(r['monthly'],[{'currency':'USD','minor':333}])
  self.assertEqual(self.report(end='2026-09-30')['annual'],[{'currency':'CNY','minor':1000}])
 def test_void_and_no_overwrite(self):
  record=self.save();self.assertEqual(self.report()['annual'][0]['minor'],12345)
  with self.assertRaises(sqlite3.IntegrityError):self.db.execute('UPDATE aftersales_expenses SET amount_minor=1 WHERE id=?',(record['id'],))
  costs.void(self.db,self.owner,{'id':record['id'],'reason':'录入错误'})
  self.assertEqual(self.report()['annual'],[])
  with self.assertRaises(core.Problem):costs.void(self.db,self.owner,{'id':record['id'],'reason':'再次作废'})
 def test_permissions_and_project_scope(self):
  p=dict(ticket_id='DEMO-SERVICE-001',category='parts',amount='1',currency='CNY',record_date='2026-10-19',reference='FORBIDDEN')
  with self.assertRaises(core.Problem):costs.save(self.db,self.sales,p)
  with self.assertRaises(core.Problem):costs.save(self.db,self.after,p)
  self.save();self.assertEqual(self.report(projects={})['annual'],[])
 def test_other_payer_not_counted(self):
  r=core.need(self.db,'service_tickets','DEMO-SERVICE-001');p=json.loads(r['payload']);p['costResponsibility']='客户承担';self.db.execute('UPDATE service_tickets SET payload=? WHERE id=?',(json.dumps(p),r['id']))
  with self.assertRaises(core.Problem):self.save()
  p['costResponsibility']='共同承担';self.db.execute('UPDATE service_tickets SET payload=? WHERE id=?',(json.dumps(p),r['id']));self.save(amount='25')
  self.assertEqual(self.report()['annual'][0]['minor'],2500)
 def test_legacy_and_duplicate_guard(self):
  demo_data.insert(self.db,'project_expenses',dict(id='LEGACY',project_id='DEMO-PROJECT-3',category='aftersales',amount_minor=4567,currency='CNY',record_date='2026-10-01',reference='LEGACY',note='旧费用',created_by=self.owner['id'],created_at=core.now(),updated_at=core.now()))
  self.assertEqual(self.report()['annual'][0]['minor'],4567)
  with self.assertRaises(core.Problem):self.save('LEGACY')
  self.save('NEW')
  with self.assertRaises(core.Problem):self.save('NEW')
 def test_closed_ticket_and_no_finance_toggle(self):
  r=core.need(self.db,'service_tickets','DEMO-SERVICE-001');p=json.loads(r['payload']);p['stage']='关闭与复盘';self.db.execute('UPDATE service_tickets SET payload=? WHERE id=?',(json.dumps(p),r['id']));self.save()
  d=ceo_dashboard.dashboard(self.db,self.owner,end='2026-10-19')
  self.assertFalse(d['finance']['enabled']);self.assertEqual(d['finance']['aftersales_expenses']['annual'][0]['minor'],12345)
  self.assertIn('公司承担的售后费用',__import__('ceo_finance').export_csv(d,'finance').decode('utf-8-sig'))
 def test_invalid_amount_and_date(self):
  for amount in ('0','-1','1.001','nan'):
   with self.assertRaises(core.Problem):self.save(amount=amount)
  with self.assertRaises(core.Problem):self.save(record_date='2099-01-01')

if __name__=='__main__':unittest.main()
