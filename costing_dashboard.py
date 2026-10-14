"""Costing view over the same authorized projects as sales and design."""
from collections import defaultdict
import os
from ceo_dashboard import local_day
import design_dashboard


def report(db, user, projects, quotes, orders, start, end, today):
    employees = {r['id']: dict(r) for r in db.execute('SELECT id,name,email FROM employees')}
    by_email = {r['email']: r['name'] for r in employees.values()}
    designs = [dict(r) for r in db.execute('SELECT * FROM design_tasks') if r['project_id'] in projects and r['status'] != 'cancelled']
    # Reuse the confirmed design dashboard's identity and owner resolution.
    design_rows = {r['id']: r for r in design_dashboard.report(db, user, projects, designs, start, end, today)['orders']}
    valid = [q for q in quotes if q.get('project_id') in projects and not q.get('archived_at') and not q.get('voided_at')]
    workflow = {}
    if os.environ.get('YIFUN_DEMO_MODE') == '1' and db.execute("SELECT 1 FROM sqlite_master WHERE name='demo_costing_workflows'").fetchone():
        workflow = {r['project_id']: dict(r) for r in db.execute('SELECT * FROM demo_costing_workflows')
                    if r['project_id'] in projects and projects[r['project_id']].get('notes') == '共享测试项目'}
    output = []
    for pid, p in projects.items():
        own = sorted([q for q in valid if q['project_id'] == pid], key=lambda q: (q['generated_at'], str(q['id'])), reverse=True)
        design = design_rows.get(pid)
        if not own and (not design or design['stage'] not in ('报价交接中', '生产交接中', '已完成')):
            continue
        latest = own[0] if own else None
        signed = [o for o in orders if o['project_id'] == pid]
        amounts = defaultdict(int)
        for order in signed:
            amounts[order['currency']] += order['agreed_minor']
        owner_rows = db.execute("SELECT employee_id FROM project_members WHERE project_id=? AND assignment_role='owner' ORDER BY employee_id", (pid,)).fetchall()
        sales = '、'.join(employees.get(r['employee_id'], {}).get('name') or '待分配' for r in owner_rows) if owner_rows else p['owner'] or '待分配'
        state = '已成交' if signed else '已确认待下单' if latest and latest['is_finalized'] else '已生成报价' if latest else '待核算'
        meta = workflow.get(pid, {})
        state = meta.get('state') or state
        output.append({'shared_test': bool(meta), 'id': pid, 'name': p['name'], 'code': p['code'],
            'sales_owner': design['sales_owner'] if design else sales,
            'design_owner': design['design_owner'] if design else '待分配',
            'costing_owner': by_email.get(latest['created_by'], '待核对') if latest else '待分配',
            'state': state, 'count': len(own), 'amounts': dict(amounts), 'due': meta.get('due_date'),
            'progress': meta.get('progress') or ('正式订单已确认，成交金额含增项' if signed else '报价已确认，等待正式下单' if latest and latest['is_finalized'] else '报价文件已生成，发送情况待登记' if latest else '设计资料已确认，等待核算报价')})
    # Revisions stay with the first effective quotation's reporting period.
    first_dates = {}
    for quote in valid:
        date = local_day(quote['generated_at'])
        if date:
            pid = quote['project_id']
            first_dates[pid] = min(first_dates.get(pid, date.isoformat()), date.isoformat())
    def count_since(day):
        return sum(day <= date <= end for date in first_dates.values())
    return {'shared_test_count': sum(r['shared_test'] for r in output), 'projects': output, 'totals': {'pending': sum(r['state'] in ('待核算','待接收') for r in output),
        'active': sum(r['state'] in ('已生成报价','核算中') for r in output), 'review': sum(r['state']=='待报价审核' for r in output) if workflow else None,
        'monthly': count_since(end[:7] + '-01'), 'annual': count_since(end[:4] + '-01-01')},
        'notices': ['标注共享测试的项目使用一套跨部门测试记录；测试状态、截止时间及发送记录仅属于模拟流程。', '项目编号、名称、商务负责人及设计负责人沿用销售和设计共用档案；核算负责人取最新有效报价创建人的员工姓名。',
            '月完成数及年核算总数量按项目去重，以首次有效报价日期归属月份和年度，同一项目的修订不重复计数。表格核算次数保留有效报价的实际次数，包含修订；已归档、已作废及未关联项目记录不计入。',
            '成交金额读取正式订单，含增项，与销售部同口径；不同币种分别显示，报价金额不作为成交金额。',
            '目前没有独立核算过程及报价审核记录，核算进行中暂以已生成但未确认的报价计数，待报价审核显示待接入。',
            '尚未登记核算截止时间和报价发送时间，分别显示待登记和发送情况待登记，不使用设计期限替代核算期限。']}
