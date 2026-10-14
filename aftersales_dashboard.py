"""售后驾驶舱：共用工单、上海日期、项目权限和显式登记。"""
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo
import core as c
import project_access as access

ZONE = ZoneInfo('Asia/Shanghai')
STAGES = ('审核', '工程下单', '生产采购', '发货物流', '现场处理', '客户验收')
METHODS = ('客户自行处理', '当地工人处理', '公司师傅上门')
RISKS = ('无安全风险', '一般安全风险', 'S级安全问题')
COSTS = ('待确认', '公司承担', '客户承担', '供应商承担', '共同承担')
LEGACY = {'接收反馈':'审核', '建立售后单':'审核', '初步分析':'工程下单', '制定方案':'工程下单', '执行处理':'现场处理', '售后回访':'客户验收'}
CLOSED = ('关闭与复盘', '已关闭', '工单关闭')


def local_date(value):
    if not value: return None
    try:
        text = str(value)
        if len(text) == 10: return date.fromisoformat(text).isoformat()
        stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=ZoneInfo('UTC'))
        return stamp.astimezone(ZONE).date().isoformat()
    except (ValueError, TypeError): return None


def phase(payload):
    stage = payload.get('stage') or '接收反馈'
    if stage in CLOSED: return '已关闭'
    registered = payload.get('dashboardStage')
    if registered in STAGES and payload.get('dashboardSourceStage') == stage: return registered
    return stage if stage in STAGES else LEGACY.get(stage, '待核对')


def save(db, user, p):
    c.permit(user, 'admin', 'ceo', 'aftersales')
    ticket = access.require(db, user, 'service_tickets', p.get('id'))
    if ticket['version'] != p.get('version'): raise c.Problem('工单已被更新，请刷新后再登记', 409)
    payload = json.loads(ticket['payload'])
    if payload.get('stage') in CLOSED: raise c.Problem('已关闭工单请在售后工作台核对', 409)
    stage = p.get('dashboard_stage') or ''
    if stage and stage not in STAGES: raise c.Problem('请选择有效流程阶段')
    values = {}
    for key, field, choices in [('execution_method','executionMethod',METHODS), ('safety_level','safetyLevel',RISKS), ('cost_responsibility','costResponsibility',COSTS)]:
        value = p.get(key) or ''
        if value and value not in choices: raise c.Problem('请选择有效登记项')
        values[field] = value
    values['contractDeadline'] = c.day(p['contract_deadline']) if p.get('contract_deadline') else ''
    values['dashboardStage'] = stage
    values['dashboardSourceStage'] = payload.get('stage') or '接收反馈'
    before = {key:payload.get(key) for key in values}
    payload.update(values)
    history = payload.get('history')
    if not isinstance(history, list): history = []
    history.append({'at':c.now(), 'action':'登记驾驶舱流程与风险', 'note':user['name']})
    payload['history'] = history
    db.execute('UPDATE service_tickets SET payload=?,version=version+1,updated_at=? WHERE id=?', (json.dumps(payload,ensure_ascii=False),c.now(),ticket['id']))
    c.audit(db,user,'service_ticket',ticket['id'],'登记驾驶舱流程与风险', {'before':before,'after':values})
    return {'ok':True}


def report(db, user, projects, today):
    employees = {r['id']:dict(r) for r in db.execute('SELECT * FROM employees')}
    members = {}
    for r in db.execute('SELECT * FROM project_members'):
        if r['project_id'] in projects:
            members.setdefault((r['project_id'],r['assignment_role']), []).append(employees.get(r['employee_id'],{}).get('name','待分配'))
    design_owners = {}
    for r in db.execute("SELECT project_id,owner_id FROM design_tasks WHERE status!='cancelled' ORDER BY updated_at"):
        if r['project_id'] in projects: design_owners[r['project_id']] = employees.get(r['owner_id'],{}).get('name','待分配')
    rows = []
    for raw in db.execute('SELECT * FROM service_tickets ORDER BY created_at DESC'):
        ticket = dict(raw); pid = ticket['project_id']
        if pid not in projects: continue
        payload = json.loads(ticket['payload']); project = projects[pid]
        due = local_date(payload.get('dueDate')); stage = phase(payload); closed = stage=='已关闭'
        method = payload.get('executionMethod') or (payload.get('handling') if payload.get('handling') in METHODS else '')
        safety = payload.get('safetyLevel') or ''
        rows.append({'id':ticket['id'],'project_id':pid,'name':project['name'], 'product':payload.get('product',''), 'description':payload.get('description',''),
            'shared_test':project.get('notes')=='共享测试项目' or payload.get('source')=='模拟测试',
            'created_date':local_date(ticket['created_at']), 'stage':stage, 'native_stage':payload.get('stage') or '接收反馈', 'closed':closed,
            'due_date':due, 'contract_deadline':local_date(payload.get('contractDeadline')),
            'overdue':not closed and bool(due and due<today), 'safety_level':safety, 'risk':not closed and safety in ('一般安全风险','S级安全问题'),
            'execution_method':method if method in METHODS else '', 'cost_responsibility':payload.get('costResponsibility',''),
            'sales_owner':'、'.join(members.get((pid,'owner'),[])) or project.get('owner') or '待分配',
            'design_owner':design_owners.get(pid) or '、'.join(members.get((pid,'design'),[])) or '待分配',
            'engineering_owner':'、'.join(members.get((pid,'engineering'),[])) or '待分配',
            'owner':payload.get('owner') or '待分配', 'version':ticket['version']})
    active = [r for r in rows if not r['closed']]
    return {'orders':rows, 'today':today, 'year':today[:4], 'month':today[:7],
        'annual_total':sum(bool(r['created_date'] and today[:4]+'-01-01'<=r['created_date']<=today) for r in rows),
        'monthly_total':sum(bool(r['created_date'] and today[:7]+'-01'<=r['created_date']<=today) for r in rows),
        'open_total':len(active), 'pending_review':sum(r['stage']=='审核' for r in active), 'overdue_total':sum(r['overdue'] for r in active),
        'pending_acceptance':sum(r['stage']=='客户验收' for r in active), 'risk_total':sum(r['risk'] for r in active),
        'stages':[{'label':s,'count':sum(r['stage']==s for r in active)} for s in STAGES],
        'methods':[{'label':m,'count':sum(r['execution_method']==m for r in active)} for m in METHODS],
        'unclassified_stage':sum(r['stage']=='待核对' for r in active), 'unregistered_method':sum(not r['execution_method'] for r in active),
        'unregistered_risk':sum(not r['safety_level'] for r in active), 'unregistered_cost':sum(not r['cost_responsibility'] for r in active),
        'safety_s':sum(r['safety_level']=='S级安全问题' for r in active), 'cost_pending':sum(r['cost_responsibility']=='待确认' for r in active),
        'can_edit':user['role'] in ('admin','ceo','aftersales'),
        'notices':['年度、月度总订单按共用工单创建时间及上海日期统计，含已关闭工单；当前状态、流程及执行方式统计未关闭工单。',
            '旧流程接收反馈／建立售后单归审核，初步分析／制定方案归工程下单，执行处理归现场处理，售后回访归客户验收；生产采购与发货物流由负责人登记。',
            '超期按预计完成日期计算；合同期限独立登记，不以预计完成日期代替。未登记的执行方式、安全与费用承担显示待登记。',
            '客户验收与关闭继续在原售后工作台办理；驾驶舱登记不代替客户验收、负责人复核、采购、物流或库存操作。原工作流改变后重新按原节点归类。']}
