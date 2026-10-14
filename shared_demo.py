"""One-time, labelled cross-department fixtures for an existing demo deployment."""
import json
import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from demo_data import insert
import core

MARKER = 'shared_department_demo_20261014_v2'


def seed(db):
    if os.environ.get('YIFUN_DEMO_MODE') != '1': return False
    if db.execute('SELECT 1 FROM settings WHERE key=?', (MARKER,)).fetchone(): return True
    if not db.execute("SELECT 1 FROM settings WHERE key='shared_demo_seed_v1'").fetchone(): return False
    owner = db.execute("SELECT * FROM employees WHERE role='admin' AND status='active' ORDER BY created_at,id LIMIT 1").fetchone()
    if not owner: return False
    # Touch only the explicitly labelled original fixtures; never infer test records by name.
    for i in range(1, 4):
        p = db.execute('SELECT notes FROM projects WHERE id=?', (f'DEMO-PROJECT-{i}',)).fetchone()
        if not p or p['notes'] != '共享测试项目': return False
    actor = dict(owner)
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    day = today.isoformat(); stamp = core.now()
    db.execute('''CREATE TABLE IF NOT EXISTS demo_costing_workflows(
        project_id TEXT PRIMARY KEY REFERENCES projects(id),state TEXT NOT NULL,
        due_date TEXT NOT NULL,progress TEXT NOT NULL,sent_at TEXT,
        source_account_id TEXT REFERENCES marketing_accounts(id))''')
    people = [('sales-a','模拟商务甲','sales'),('sales-b','模拟商务乙','sales'),
              ('design-a','模拟设计甲','engineering'),('design-b','模拟设计乙','engineering'),
              ('cost-a','模拟核算甲','sales'),('cost-b','模拟核算乙','sales')]
    for key, name, role in people:
        if not db.execute('SELECT 1 FROM employees WHERE id=?', ('DEMO-'+key,)).fetchone():
            insert(db,'employees',dict(id='DEMO-'+key,email=key+'@example.invalid',name=name,role=role,
                status='active',password_hash=secrets.token_hex(32),salt=secrets.token_hex(16),created_at=stamp))
    names = ['模拟内贸乐园项目','模拟海外设备项目','模拟配件交付项目','模拟亲子探索馆项目','模拟主题乐园项目','模拟室内游乐项目']
    states = ['已报价','待接收','已成交','核算中','待报价审核','已成交']
    progresses = ['报价已发出，等待客户确认','设计资料已交接，等待核算接收','最终成交已确认，转工程交接',
                  '设备成本已核对，运输与安装费用核算中','报价已整理，等待负责人审核','外贸订单已确认，设计与生产资料已交接']
    counts = [2,0,3,1,2,1]
    accounts = [dict(r) for r in db.execute('SELECT id,market,platform,name FROM marketing_accounts ORDER BY CAST(id AS INTEGER)')]
    for i in range(1, 7):
        pid=f'DEMO-PROJECT-{i}'; cid=f'DEMO-CUSTOMER-{i}'
        sales='DEMO-sales-'+('a' if i%2 else 'b'); designer='DEMO-design-'+('a' if i%2 else 'b'); cost='DEMO-cost-'+('a' if i%2 else 'b')
        # A user-created quotation on an original fixture takes precedence over the fixture expansion.
        if db.execute("SELECT 1 FROM quotation_history WHERE project_id=? AND id NOT LIKE 'DEMO-FLOW-%'",(pid,)).fetchone(): continue
        if i > 3:
            if db.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone(): continue
            insert(db,'customers',dict(id=cid,code=f'DEMO-C{i:03}',name=f'模拟客户 {i}',contact='模拟联系人',
                email=f'customer-{i}@example.invalid',notes='共享测试数据，非正式业务资料',created_by=actor['id'],created_at=stamp))
            insert(db,'projects',dict(id=pid,code=f'DEMO-P{i:03}',name=names[i-1],customer_id=cid,
                location='中国' if i!=6 else '美国',owner='模拟商务甲' if i%2 else '模拟商务乙',notes='共享测试项目',created_at=stamp))
        for member in (sales,designer,cost):
            if member==sales:
                db.execute("UPDATE project_members SET assignment_role='member' WHERE project_id=? AND assignment_role='owner'",(pid,))
            db.execute('INSERT INTO project_members VALUES(?,?,?,?,?) ON CONFLICT(project_id,employee_id) DO UPDATE SET assignment_role=excluded.assignment_role',
                (pid,member,'owner' if member==sales else 'member',actor['id'],stamp))
        due=(today+timedelta(days=i-1)).isoformat()
        design_id=f'DEMO-DESIGN-{i}'
        task=db.execute('SELECT * FROM design_tasks WHERE id=?',(design_id,)).fetchone()
        if not task:
            insert(db,'design_tasks',dict(id=design_id,number=f'DEMO-D{i:03}',project_id=pid,title=f'模拟方案设计 {i}',
                task_type='方案设计',brief='共享测试项目设计资料',requested_date=day,owner_id=designer,
                created_by=actor['id'],created_at=stamp,updated_at=stamp))
        # Only advance untouched original seed tasks, leaving user edits intact.
        if not task or task['status']=='queued' and not task['result_reference']:
            ds='accepted' if i==6 else 'handoff' if i==3 else 'confirmed'
            db.execute('''UPDATE design_tasks SET status=?,owner_id=?,team=?,version_label='V1',due_date=?,original_due_date=?,
                confirmation='共享测试：客户已确认方案',result_reference='共享测试设计资料',accepted_at=?,updated_at=? WHERE id=?''',
                (ds,designer,'设计一组' if i%2 else '设计二组',due,due,stamp if i==6 else None,stamp,design_id))
        lead=f'DEMO-LEAD-{i}'
        market='外贸' if i in (2,6) else '内贸'
        account=next((a for a in accounts if a['market']==market),None)
        source=(account['platform']+' · '+account['name']) if account else '共享测试渠道'
        if not db.execute('SELECT 1 FROM crm_leads WHERE id=?',(lead,)).fetchone():
            insert(db,'crm_leads',dict(id=lead,name=f'模拟来源线索 {i}',company=f'模拟公司 {i}',contact='模拟联系人',
                source=source,owner_id=sales,next_date=day,next_action='共享测试项目跟进',notes='非真实客户线索',
                customer_id=cid,created_by=actor['id'],created_at=stamp,updated_at=stamp))
        db.execute('UPDATE crm_leads SET owner_id=?,source=?,region=?,customer_grade=? WHERE id=?',
            (sales,source,'中国' if market=='内贸' else '美国','A' if i in (1,3,6) else 'B',lead))
        insert(db,'marketing_lead_allocations',dict(id=f'DEMO-FLOW-ALLOC-{i}',lead_id=lead,owner_id=sales,assigned_by=actor['id'],assigned_at=stamp))
        currency='USD' if i in (2,6) else 'CNY'; amount=58000 if i==6 else 348000 if i==3 else 360000
        insert(db,'crm_opportunities',dict(id=f'DEMO-FLOW-OPP-{i}',lead_id=lead,customer_id=cid,project_id=pid,
            name=names[i-1]+' · 测试商机',owner_id=sales,stage='won' if i in (3,6) else 'negotiation' if i==1 else 'quotation',
            expected_minor=amount*100,currency=currency,expected_date=due,next_action=progresses[i-1],notes='共享测试数据',
            created_by=actor['id'],created_at=stamp,updated_at=stamp))
        for version in range(1, counts[i-1]+1):
            qid=f'DEMO-FLOW-QUOTE-{i}-{version}'
            snapshot={'workspaceProjectId':pid,'workspaceDocumentKind':'original','projectName':names[i-1],
                'contractNo':f'DEMO-Q{i:03}-V{version}','items':[], 'sharedDemo':True,'version':version}
            is_last=version==counts[i-1]
            confirmed=i in (1,3,6) and is_last
            insert(db,'quotation_history',dict(id=qid,contract_no=f'DEMO-Q{i:03}-V{version}',project_name=names[i-1],
                created_by=cost.removeprefix('DEMO-')+'@example.invalid',snapshot_json=json.dumps(snapshot,ensure_ascii=False),
                generated_at=(datetime.now(ZoneInfo('Asia/Shanghai'))-timedelta(minutes=counts[i-1]-version)).isoformat(),
                lineage_id=f'DEMO-FLOW-LINEAGE-{i}',is_finalized=int(confirmed),final_amount=amount if confirmed else None,
                final_currency=currency if confirmed else None,confirmed_at=stamp if confirmed else None,
                confirmed_by=actor['email'] if confirmed else '',project_id=pid,document_type='original'))
            if i in (3,6) and is_last:
                insert(db,'order_baselines',dict(id=f'DEMO-FLOW-ORDER-{i}',number=f'DEMO-SO{i:03}',project_id=pid,quote_id=qid,
                    kind='original',currency=currency,agreed_minor=amount*100,raw_snapshot=json.dumps(snapshot,ensure_ascii=False),
                    created_by=sales,created_at=stamp))
                db.execute('UPDATE quotation_history SET ordered_at=? WHERE id=?',(stamp,qid))
        insert(db,'demo_costing_workflows',dict(project_id=pid,state=states[i-1],due_date=due,progress=progresses[i-1],
            sent_at=stamp if i in (1,3,6) else None,source_account_id=account['id'] if account else None))
    insert(db,'settings',dict(key=MARKER,value=stamp))
    core.audit(db,actor,'demo',MARKER,'补齐跨部门共享测试流程',{'synthetic':True,'project_prefix':'DEMO-PROJECT-'})
    return True
