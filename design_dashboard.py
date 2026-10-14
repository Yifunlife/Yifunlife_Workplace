"""Design order dashboard over authorized shared project records."""
from collections import defaultdict
import json
from ceo_dashboard import local_day

STAGES = ('设计排单', '设计中', '报价交接中', '生产交接中')
TEAMS = ('设计一组', '设计二组', '设计三组', '设计四组')


def stage(tasks):
    states = {t['status'] for t in tasks if t['status'] != 'cancelled'}
    if not states: return '未建设计任务'
    if states <= {'accepted'}: return '已完成'
    if states & {'queued', 'waiting_materials'}: return STAGES[0]
    if states & {'in_progress', 'review', 'revising', 'waiting_confirmation'}: return STAGES[1]
    if 'confirmed' in states: return STAGES[2]
    return STAGES[3]


def completed_date(tasks):
    active = [t for t in tasks if t['status'] != 'cancelled']
    if not active or any(t['status'] != 'accepted' or not t.get('accepted_at') for t in active): return None
    return max(local_day(t['accepted_at']).isoformat() for t in active)


def report(db, user, projects, tasks, start, end, today):
    employees = {r['id']:r['name'] for r in db.execute('SELECT id,name FROM employees')}
    def person(key): return employees.get(key) or '待分配'
    grades = defaultdict(set)
    for lead in db.execute('SELECT customer_id,customer_grade FROM crm_leads'):
        if lead['customer_id'] and lead['customer_grade']: grades[lead['customer_id']].add(lead['customer_grade'])
    metadata = {}
    for raw in db.execute('SELECT project_id,customer_id,payload FROM connected_sales WHERE active=1 ORDER BY rowid'):
        if raw['project_id'] not in projects: continue
        payload = json.loads(raw['payload']); metadata[raw['project_id']] = payload
        grade = str(payload.get('grade') or '').replace('类','').strip().upper()
        if grade in ('A','B','C'): grades[raw['customer_id']].add(grade)
    orders = defaultdict(list)
    for raw in db.execute('SELECT * FROM order_baselines ORDER BY created_at,number'):
        if raw['project_id'] in projects: orders[raw['project_id']].append(dict(raw))
    output = []
    for pid, p in projects.items():
        design = [t for t in tasks if t['project_id'] == pid and t['status'] != 'cancelled']
        if not design: continue
        current = stage(design); completed = completed_date(design)
        teams = {t['team'].strip() for t in design if t['team'].strip()}
        team = next(iter(teams)) if len(teams)==1 else '跨组订单' if teams else '待分组'
        owner = db.execute("SELECT employee_id FROM project_members WHERE project_id=? AND assignment_role='owner' ORDER BY employee_id",(pid,)).fetchall()
        amounts = defaultdict(int)
        for order in orders[pid]: amounts[order['currency']] += order['agreed_minor']
        overdue = current != '已完成' and any(t['original_due_date'] and t['original_due_date'] < today and t['status'] != 'accepted' for t in design)
        alerts = []
        if overdue: alerts.append('设计逾期')
        if any(t['status']=='waiting_materials' for t in design): alerts.append('待补资料')
        if any(t['priority']=='urgent' for t in design): alerts.append('紧急订单')
        if any(t['status']=='waiting_confirmation' for t in design): alerts.append('待客户确认')
        if current == STAGES[2]: alerts.append('核算部待接收报价资料')
        if current == STAGES[3]: alerts.append('工程部待接收生产资料')
        customer_grades = grades[p['customer_id']]
        output.append({'id':pid,'name':p['name'],'code':p['code'],'order_numbers':[o['number'] for o in orders[pid] if o['kind']=='original'],
            'amounts':dict(amounts),'customer_grade':next(iter(customer_grades)) if len(customer_grades)==1 else '标签冲突待核对' if customer_grades else '待确认',
            'project_type':metadata.get(pid,{}).get('project_type') or metadata.get(pid,{}).get('projectType') or '待确认',
            'sales_owner':'、'.join(person(r['employee_id']) for r in owner) if owner else p['owner'] or '待分配',
            'design_owner':'、'.join(dict.fromkeys(person(t['owner_id']) for t in design)), 'team':team,'stage':current,
            'expected_date':max((t['due_date'] for t in design if t['due_date']),default=None),'actual_date':completed,'overdue':overdue,'alerts':alerts})
    def totals(rows):
        return {'annual':sum(bool(r['actual_date'] and end[:4]+'-01-01'<=r['actual_date']<=end) for r in rows),
            'monthly':sum(bool(r['actual_date'] and end[:7]+'-01'<=r['actual_date']<=end) for r in rows),
            'active':sum(r['stage']!='已完成' for r in rows),
            'stages':[sum(r['stage']==s for r in rows) for s in STAGES], 'overdue':sum(r['overdue'] for r in rows)}
    names = list(TEAMS) + sorted({r['team'] for r in output}-set(TEAMS))
    return {'orders':output,'totals':totals(output),'groups':[{'name':name,**totals([r for r in output if r['team']==name])} for name in names],
        'notices':['订单按关联项目去重，增项只计金额，不增加设计订单数；未签单项目保留项目编号，订单金额显示待确认。',
            '设计排单读取待排或待资料；设计中包含内部审核、修改及待客户确认；报价交接中读取客户已确认；生产交接中读取待工程接收。生产资料由工程部接收后转入生产流程。',
            '设计完成以全部有效设计任务由工程接收为准，实际完成日期取最后一次接收日期；销售部同步采用同一口径。',
            '客户等级沿用运营及同步客户标签；项目类型未登记时显示待确认，不按项目名称猜测。不同币种分别展示。',
            '四组名称沿用设计组字段；未分组、跨组及其他历史组单列，确保组汇总等于部门总数。逾期按未接收任务首次承诺日期统计。']}
