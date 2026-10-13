"""Company overview calculated from shared records, with explicit metric definitions."""
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import core
import ceo_finance
import account_reporting
from marketing_reporting import advertising_records

REPORTING_ZONE = ZoneInfo('Asia/Shanghai')


def local_day(value):
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return moment.replace(tzinfo=timezone.utc).astimezone(REPORTING_ZONE).date() if moment.tzinfo is None else moment.astimezone(REPORTING_ZONE).date()
    except (TypeError, ValueError, AttributeError):
        return None


def calendar_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def dashboard(db, user, start=None, end=None, at=None, project_id=None):
    core.permit(user, 'ceo', 'admin')
    moment = at or datetime.now(timezone.utc)
    today = moment.astimezone(REPORTING_ZONE).date()
    start = date.fromisoformat(core.day(start)) if start else today.replace(day=1)
    end = date.fromisoformat(core.day(end)) if end else today
    if start > end:
        raise core.Problem('开始日期不能晚于结束日期')
    overview = core.view(db, user, 'overview')
    options = [{'id':p['id'],'code':p['code'],'name':p['name']} for p in overview['projects']]
    if project_id:
        core.access.require(db,user,'projects',project_id)
    projects = {p['id']: p for p in overview['projects'] if not project_id or p['id']==project_id}
    baselines = [b for b in overview['baselines'] if b['project_id'] in projects]
    baseline_map = {b['id']: b for b in baselines}
    employees = {r['id']: r['name'] for r in db.execute('SELECT id,name FROM employees')}
    orders = [dict(r) for r in db.execute('''SELECT po.id,po.po_number,po.project_name,po.purchaser_name,
        po.required_ship_date,po.promised_ship_date,pc.project_id,pc.purpose,
        COALESCE(SUM(i.quantity),0) quantity,COALESCE(SUM(i.shipped_quantity),0) shipped,
        COALESCE(SUM(i.stocked_quantity),0) stocked
        FROM purchase_orders po LEFT JOIN procurement_context pc ON pc.order_id=po.id
        LEFT JOIN order_items i ON i.order_id=po.id WHERE po.archived_at IS NULL GROUP BY po.id''')]
    orders = [o for o in orders if not project_id or o['project_id']==project_id]
    tickets = []
    closed_tickets = 0
    for r in db.execute('SELECT * FROM service_tickets ORDER BY created_at DESC'):
        payload = json.loads(r['payload'])
        if r['project_id'] not in projects:
            continue
        if payload.get('stage') == '关闭与复盘':
            closed_tickets += 1
            continue
        tickets.append({'id': r['id'], 'project_id': r['project_id'],
                        'project_name': projects[r['project_id']]['name'], 'product': payload.get('product', ''),
                        'description': payload.get('description', ''), 'stage': payload.get('stage') or '接收反馈',
                        'owner': payload.get('owner') or '待分配', 'due_date': payload.get('dueDate'),
                        'created_at': r['created_at'], 'updated_at': r['updated_at']})
    period_orders = [{k: b[k] for k in ('id', 'number', 'project_id', 'project_name', 'kind', 'currency', 'agreed_minor', 'created_at')}
                     for b in baselines if local_day(b['created_at']) and start <= local_day(b['created_at']) <= end]
    countries = {}
    for row in db.execute('SELECT project_id,payload FROM connected_sales WHERE active=1'):
        countries[row['project_id']] = str(json.loads(row['payload']).get('country') or '').strip()
    def contract_market(project_id):
        country = countries.get(project_id) or str(projects[project_id].get('location') or '').strip()
        normalized = country.casefold().replace(' ', '')
        if not normalized or normalized in ('unknown','待确认','未填写','其他'):
            return 'unknown'
        if normalized in ('cn','chn','china','中国','中国大陆','mainlandchina','prc','中华人民共和国'):
            return 'domestic'
        return 'overseas'
    contract_periods = {}
    for key,begin in (('annual',end.replace(month=1,day=1)),('monthly',end.replace(day=1))):
        records = [{k:b[k] for k in ('id','number','project_id','project_name','kind','currency','agreed_minor','created_at')} for b in baselines if local_day(b['created_at']) and begin <= local_day(b['created_at']) <= end]
        aggregate = defaultdict(int)
        markets = {k:{'count':0,'amounts':[]} for k in ('domestic','overseas','unknown')}
        market_totals = {k:defaultdict(int) for k in markets}
        for b in records:
            b['market'] = contract_market(b['project_id'])
            aggregate[b['currency']] += b['agreed_minor']
            markets[b['market']]['count'] += 1
            market_totals[b['market']][b['currency']] += b['agreed_minor']
        for market in markets:
            markets[market]['amounts'] = ceo_finance.amounts(market_totals[market])
        contract_periods[key] = {'from':begin.isoformat(),'to':end.isoformat(),'amounts':ceo_finance.amounts(aggregate),'orders':records,'markets':markets}
    annual_expenses = {
        'salary': {'label':'年度工资支出','connected':False,'amounts':[],'records':[]},
        'premises': {'label':'年度房租水电费支出','connected':False,'amounts':[],'records':[]},
        'advertising': {'label':'年度广告费支出（含展会）','connected':True,'amounts':[],'records':[]}
    }
    advertising = annual_expenses['advertising']
    for r in advertising_records(db,end.replace(month=1,day=1).isoformat(),end.isoformat(),project_id):
        advertising['records'].append({'date':r['record_date'],'number':r['number'],'category':r['expense_type'],'channel':r['channel'],'activity':r['activity'],'currency':r['currency'],'minor':r['amount_minor']})
    spend_totals=defaultdict(int)
    for r in advertising['records']:spend_totals[r['currency']]+=r['minor']
    advertising['amounts']=ceo_finance.amounts(spend_totals)
    totals = defaultdict(int)
    for b in period_orders:
        totals[b['currency']] += b['agreed_minor']
    decisions = []
    for r in overview['releases']:
        if r['status'] != 'pending' or r['baseline_id'] not in baseline_map:
            continue
        b = baseline_map[r['baseline_id']]
        decisions.append({**r, 'project_id': b['project_id'], 'currency': b['currency'],
                          'agreed_minor': b['agreed_minor'], 'requested_by_name': employees.get(r['requested_by'], '待确认'),
                          'waiting_days': max(0, (today - local_day(r['created_at'])).days)})
    exceptions = []

    def issue(kind, key, project_id, title, detail, owner, target, target_id, due=None):
        if project_id not in projects and not any(o['id']==target_id for o in orders):
            return
        exceptions.append({'id': kind + ':' + key, 'kind': kind, 'project_id': project_id,
                           'project_name': projects[project_id]['name'] if project_id in projects else '仓库备货' if target_id in {o['id'] for o in orders if o['purpose'] == 'stock'} else '待关联项目',
                           'title': title, 'detail': detail, 'owner': owner or '待分配',
                           'target': target, 'target_id': target_id, 'due_date': due.isoformat() if due else None,
                           'overdue_days': (today - due).days if due else None})

    for order in orders:
        due = calendar_day(order['promised_ship_date'] or order['required_ship_date'])
        if due and due < today and order['shipped'] < order['quantity']:
            issue('purchase_overdue', order['id'], order['project_id'], '采购发货逾期',
                  order['po_number'] + ' · 仍有产品未发货', order['purchaser_name'], 'procurement', order['id'], due)
    for receipt in db.execute('''SELECT r.id,r.order_id,r.exception_type,r.exception_notes,pc.project_id,p.po_number,p.purchaser_name
        FROM warehouse_receipts r JOIN purchase_orders p ON p.id=r.order_id
        LEFT JOIN procurement_context pc ON pc.order_id=p.id WHERE r.status='exception' AND p.archived_at IS NULL'''):
        issue('warehouse_exception', receipt['id'], receipt['project_id'], '到货验收异常',
              receipt['po_number'] + ' · ' + (receipt['exception_notes'] or receipt['exception_type'] or '请核对验收记录'),
              receipt['purchaser_name'], 'procurement', receipt['order_id'])
    for ticket in tickets:
        due = calendar_day(ticket['due_date'])
        if due and due < today:
            issue('service_overdue', ticket['id'], ticket['project_id'], '售后处理逾期',
                  ticket['id'] + ' · ' + ticket['description'], ticket['owner'], 'aftersales', ticket['id'], due)
    for project in projects.values():
        if not project['owner_id'] or not project['member_count']:
            issue('unassigned', project['id'], project['id'], '项目负责人待分配',
                  '请管理员选择员工账号，历史姓名不会自动授予权限', '', 'members', project['id'])
    for task in db.execute("SELECT * FROM work_tasks WHERE status NOT IN ('done','accepted','closed')"):
        due=calendar_day(task['due_date'])
        if task['blocking'] or (due and due<today):
            target={'task':'tasks','installation':'installation','issue':'issues'}[task['kind']]
            issue('project_task',task['id'],task['project_id'],'影响安装或交付' if task['blocking'] else '项目事项逾期',task['title'],employees.get(task['owner_id']),'operations-'+target,task['id'],due if due and due<today else None)
    exceptions.sort(key=lambda e: (-(e['overdue_days'] or 0), e['kind'], e['id']))
    tracking = []
    tasks = [dict(t) for t in db.execute('SELECT * FROM work_tasks') if t['project_id'] in projects]
    engineering = [dict(e) for e in db.execute("SELECT * FROM engineering_orders WHERE status='released'") if e['project_id'] in projects]
    for project in projects.values():
        linked = [b for b in baselines if b['project_id'] == project['id']]
        lines = [line for b in linked for line in b['lines'] if line['effective_quantity'] > 0]
        finished = sum(line['delivered'] >= line['effective_quantity'] - 1e-6 for line in lines)
        open_tickets = [t for t in tickets if t['project_id'] == project['id']]
        purchases = [o for o in orders if o['project_id'] == project['id']]
        changes = [c for c in overview['changes'] if c['project_id'] == project['id'] and c['status'] != 'applied']
        quotations = [q for q in overview['quotations'] if q['project_id']==project['id'] and not q['archived_at'] and not q['voided_at'] and not q['ordered_at']]
        installation = [t for t in tasks if t['project_id']==project['id'] and t['kind']=='installation']
        if not linked:
            stage = '已确认待下单' if any(q['is_finalized'] for q in quotations) else '报价中' if quotations else '方案准备中'
            next_step = '销售确认报价及成交范围'
        elif not lines:
            stage, next_step = '需求已取消', '核对已采购实物及客户差额'
        elif finished == len(lines):
            stage, next_step = '交付完成', '跟进客户使用情况'
        elif any(not any(e['baseline_id']==b['id'] for e in engineering) for b in linked):
            stage, next_step = '待工程下单', '工程核对规格、图纸及执行去向后下达工程单'
        elif any(not b['release_route'] and any(l['effective_quantity']>l['delivered']+1e-6 for l in b['lines']) for b in linked):
            stage, next_step = '待放行', '核对订金条件或等待 CEO 审批'
        elif any(line['allocated'] < line['effective_quantity'] - line['delivered'] - 1e-6 for line in lines):
            stage, next_step = '待采购或配货', '采购与仓库核对剩余需求'
        elif any(o['stocked'] < o['quantity'] for o in purchases):
            stage = '待收货验收' if all(o['shipped']>=o['quantity'] for o in purchases) else '采购执行中'
            next_step = '跟进采购发货、收货和验收'
        else:
            stage, next_step = '待交付', '仓库确认实际型号与客户发货'
        if changes:
            next_step = '销售确认变更' if any(c['status'] == 'draft' for c in changes) else '采购执行已确认变更'
        if stage == '交付完成' and any(t['status']!='accepted' for t in installation):
            stage, next_step = '安装与验收中', '现场完成安装并留存客户验收记录'
        elif open_tickets and stage == '交付完成':
            stage, next_step = '售后跟进中', '售后处理并确认关闭'
        own_exceptions = [e for e in exceptions if e['project_id'] == project['id']]
        dated = [(calendar_day(t['due_date']),'安装要求完成') for t in installation if t['status']!='accepted']
        dated += [(calendar_day(o['promised_ship_date'] or o['required_ship_date']),'采购约定发货') for o in purchases if o['shipped']<o['quantity']]
        dated = sorted((d,s) for d,s in dated if d)
        due, due_source = dated[0] if dated else (None,'尚未安排')
        contract = defaultdict(int)
        period_amount = defaultdict(int)
        for b in linked:
            contract[b['currency']] += b['agreed_minor']
        for b in period_orders:
            if b['project_id']==project['id']:period_amount[b['currency']] += b['agreed_minor']
        quote_amount = defaultdict(int)
        # The most recent active original quotation avoids adding revised versions twice.
        original_quotes = [q for q in quotations if q.get('quote_kind', 'original') == 'original']
        if original_quotes:
            q = original_quotes[0]
            if q.get('final_amount') is not None and q.get('final_currency'):
                quote_amount[q['final_currency']] += round(float(q['final_amount']) * 100)
        lifecycle = {'方案准备中':'设计中','报价中':'报价中','已确认待下单':'已报价待签单',
                     '待工程下单':'工程下单','待放行':'工程下单'}.get(stage)
        if stage in ('交付完成','售后跟进中') and installation and all(t['status']=='accepted' for t in installation):
            lifecycle = '已完成'
        elif lines and finished == len(lines):
            pending_installation = [t for t in installation if t['status'] != 'accepted']
            lifecycle = '安装中' if any(t['status'] in ('in_progress', 'awaiting_acceptance') for t in pending_installation) else '已发货待安装' if not installation or pending_installation else '已完成'
        tracking.append({**project, 'lifecycle_stage': lifecycle, 'signed': bool(linked), 'quote_amounts': ceo_finance.amounts(quote_amount), 'stage': stage, 'next_step': next_step, 'completed_lines': finished,
                         'total_lines': len(lines), 'open_tickets': len(open_tickets), 'pending_changes': len(changes),
                         'exception_count': len(own_exceptions), 'executing': bool(linked and lines and finished < len(lines)),
                         'purchase_ids': [o['id'] for o in purchases], 'ticket_ids': [t['id'] for t in open_tickets],
                         'progress':round(finished/len(lines)*100,1) if lines else None,
                         'contract_amounts':ceo_finance.amounts(contract),'period_amounts':ceo_finance.amounts(period_amount),
                         'due_date':due.isoformat() if due else None,'due_source':due_source,'days_remaining':(due-today).days if due else None,
                         'installation_count':len(installation),'accepted_installations':sum(t['status']=='accepted' for t in installation)})
    tracking.sort(key=lambda p: (-p['exception_count'], p['code']))
    customers=[]
    for customer in overview['customers']:
        own=[p for p in tracking if p['customer_id']==customer['id']]
        if not own:continue
        linked=[b for b in baselines if b['project_id'] in {p['id'] for p in own}]
        totals_customer=defaultdict(int)
        for b in linked:totals_customer[b['currency']]+=b['agreed_minor']
        customers.append({'id':customer['id'],'name':customer['name'],'project_count':len(own),
                          'cooperation_count':len({b['project_id'] for b in linked}),
                          'amounts':ceo_finance.amounts(totals_customer),'project_ids':[p['id'] for p in own]})
    finance=ceo_finance.report(db,baselines,tracking,start,end,local_day,include_stock=not project_id)
    account_report=account_reporting.report(db,start.isoformat(),end.isoformat(),today.isoformat()) if not project_id else None
    return {'account_reporting':account_report,'period': {'from': start.isoformat(), 'to': end.isoformat(), 'timezone': 'Asia/Shanghai'},
            'updated_at': moment.isoformat(), 'amounts': [{'currency': c, 'minor': n} for c, n in sorted(totals.items())],
            'annual_expenses': annual_expenses, 'contract_periods': contract_periods, 'period_orders': period_orders, 'projects': tracking, 'tickets': tickets, 'exceptions': exceptions,
            'decisions': decisions, 'executing_count': sum(p['executing'] for p in tracking),
            'finance_status': '已接入' if finance['enabled'] else '暂未接入', 'crm_status': '商机已接入，转化指标待定义',
            'project_options':options,'selected_project':project_id or '', 'customers':customers,'closed_tickets':closed_tickets,
            'finance':finance,'health':{'total':len(tracking),'risk':sum(p['exception_count']>0 for p in tracking),
            'overdue':len({e['project_id'] for e in exceptions if e['overdue_days'] and e['project_id'] in projects}),
            'upcoming':sum(p['days_remaining'] is not None and 0<=p['days_remaining']<=30 for p in tracking)}}
