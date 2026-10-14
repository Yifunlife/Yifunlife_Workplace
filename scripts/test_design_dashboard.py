import sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import design_dashboard as d
c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
c.executescript('''CREATE TABLE employees(id,name);CREATE TABLE crm_leads(customer_id,customer_grade);CREATE TABLE connected_sales(project_id,customer_id,payload,active);CREATE TABLE order_baselines(project_id,number,kind,currency,agreed_minor,created_at);CREATE TABLE project_members(project_id,employee_id,assignment_role);''')
c.execute("INSERT INTO employees VALUES('e','设计员')")
c.execute("INSERT INTO crm_leads VALUES('c','A')")
c.execute("INSERT INTO order_baselines VALUES('p','SO1','original','CNY',10000,'2026-01-01')")
c.execute("INSERT INTO order_baselines VALUES('p','SO2','addition','USD',500,'2026-01-02')")
p={'p':{'id':'p','name':'项目','code':'P1','customer_id':'c','owner':'商务'}}
t={'project_id':'p','status':'accepted','accepted_at':'2026-10-09T10:00:00+08:00','team':'设计三组','owner_id':'e','due_date':'2026-10-10','original_due_date':'2026-10-10','priority':'normal'}
r=d.report(c,{},p,[t,t.copy()],'2026-10-01','2026-10-14','2026-10-14')
assert r['totals']['annual']==r['totals']['monthly']==1
assert r['totals']['active']==0
assert r['orders'][0]['amounts']=={'CNY':10000,'USD':500}
assert r['orders'][0]['customer_grade']=='A'
assert r['orders'][0]['project_type']=='待确认'
assert sum(g['monthly'] for g in r['groups'])==1
assert r['orders'][0]['order_numbers']==['SO1']
for status,stage in [('queued','设计排单'),('waiting_confirmation','设计中'),('confirmed','报价交接中'),('handoff','生产交接中')]:
 t.update(status=status,accepted_at=None)
 assert d.stage([t])==stage
 assert d.completed_date([t]) is None
 t['original_due_date']='2026-10-01'
 r=d.report(c,{},p,[t],'2026-10-01','2026-10-14','2026-10-14')
 assert r['totals']['overdue']==1
 assert sum(g['active'] for g in r['groups'])==r['totals']['active']==1
assert d.stage([dict(t,status='cancelled')])=='未建设计任务'
print('PASS: project dedup, annual/monthly/group totals, currencies, customer grades, four stages, overdue and completion dates')
