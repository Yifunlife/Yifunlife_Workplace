"""Read-only, account-scoped work reminders shared by every Workplace page."""
from datetime import datetime, date
from zoneinfo import ZoneInfo
import json
import core as c
import project_access as access
import centers
import operations

ZONE = ZoneInfo('Asia/Shanghai')
ROLE_CENTERS = {'sales':('crm','quote'), 'purchasing':('procurement',),
                'engineering':('engineering','factory'), 'warehouse':('stock',),
                'installation':('engineering',), 'aftersales':('aftersales',),
                'finance':('finance',)}
CLOSED = {'done','accepted','closed','cancelled'}


def report(db, user, center=None, project=None, today=None):
    today = today or datetime.now(ZONE).date().isoformat()
    day = date.fromisoformat(today)
    if user['role']!='supplier':
        import aftercare_sync
        aftercare_sync.refresh(db)
    allowed = centers.available(db, user)
    if user['role'] == 'supplier': allowed = ['procurement']
    if center and center not in allowed: raise c.Problem('没有此中心的使用权限',403)
    if project: access.require(db,user,'projects',project)
    managers = user['role'] in ('admin','ceo')
    projects = {r['id']:dict(r) for r in db.execute('SELECT * FROM projects')
                if access.visible_project(db,user,r['id'])}
    employees = {r['id']:dict(r) for r in db.execute('SELECT id,name,email,role,status FROM employees')}
    memberships = {}
    for row in db.execute('SELECT employee_id,center FROM center_members'):
        memberships.setdefault(row['employee_id'],set()).add(row['center'])
    collected = []

    def owner_centers(owner):
        employee = employees.get(owner,{})
        return set(ROLE_CENTERS.get(employee.get('role'),())) | memberships.get(owner,set())

    def add(source, key, title, page, pid=None, owner=None, due=None, scope=(),
            status='', blocked=False, note='', personal=False, module_link=''):
        if pid and pid not in projects: return
        if project and pid != project: return
        scope = set(scope)
        if not scope: scope = owner_centers(owner)
        # Generic tasks without a department remain visible in all authorized centers.
        if not scope: scope = set(allowed)
        scope &= set(allowed)
        if not scope: return
        employee = employees.get(owner,{})
        owner_name = employee.get('name') or '待分配'
        if due:
            try: due = date.fromisoformat(str(due)[:10]).isoformat()
            except ValueError: due = None
        delta = (date.fromisoformat(due)-day).days if due else None
        urgency = 'overdue' if delta is not None and delta < 0 else 'today' if delta == 0 else 'soon' if delta is not None and delta <= 3 else 'pending'
        mine = personal or owner == user['id']
        risk = blocked or urgency == 'overdue' or not owner
        collected.append({'id':source+':'+str(key),'record_id':str(key),'source':source,
            'title':title,'page':page,'project_id':pid,'project_name':projects.get(pid,{}).get('name',''),
            'owner_id':owner,'owner':owner_name,'due_date':due,'days':delta,'urgency':urgency,
            'status':status,'blocked':bool(blocked),'note':note,'mine':mine,'risk':risk,
            'centers':sorted(scope),'module_link':module_link})

    if user['role'] != 'supplier':
        for row in db.execute('SELECT * FROM work_tasks'):
            r=dict(row)
            if r['status'] in CLOSED: continue
            if not managers and not access.visible_project(db,user,r['project_id']): continue
            page={'task':'tasks','installation':'installation','issue':'issues'}[r['kind']]
            if r['status']=='resolved' and r['kind']=='issue':
                owner=r['created_by']; status='待现场确认'
            else: owner=r['owner_id']; status=r['status']
            scope=('engineering',) if r['kind']=='installation' else owner_centers(owner)
            add('task',r['id'],r['title'],page,r['project_id'],owner,r['due_date'],scope,
                status,r['blocking'] or r['status']=='blocked',r['description'])
        if 'design' in allowed:
            for row in db.execute('SELECT * FROM design_tasks'):
                r=dict(row)
                if r['status'] in ('accepted','cancelled'): continue
                try: centers.record(db,user,'design',r['id'])
                except c.Problem: continue
                owner=r['owner_id']; scope=['design']
                # Sales confirms client approval; engineering receives the handoff.
                if r['status']=='waiting_confirmation':
                    owner=projects.get(r['project_id'],{}).get('owner_id'); scope+=['crm']
                elif r['status']=='handoff':
                    member=db.execute("SELECT m.employee_id FROM project_members m JOIN employees e ON e.id=m.employee_id WHERE m.project_id=? AND e.role='engineering' AND e.status='active' ORDER BY m.employee_id",(r['project_id'],)).fetchall()
                    owner=member[0][0] if len(member)==1 else None; scope+=['engineering']
                add('design',r['id'],r['title'],'center-design-records',r['project_id'],owner,
                    r['due_date'],scope,centers.DESIGN_STATES[r['status']],
                    r['status']=='waiting_materials',r['brief'])
        for page,table,closed in [('leads','crm_leads',('lost',)),('opportunities','crm_opportunities',('won','lost'))]:
            if not (set(allowed)&{'crm','marketing'}): continue
            for row in db.execute('SELECT * FROM '+table):
                r=dict(row)
                if not operations.allowed(db,user,page,r): continue
                if r.get('status',r.get('stage')) in closed: continue
                due=r.get('next_date') or r.get('expected_date')
                latest=db.execute('SELECT next_date,next_action FROM crm_followups WHERE entity=? AND entity_id=? ORDER BY contact_date DESC,created_at DESC,rowid DESC LIMIT 1',(page,r['id'])).fetchone()
                if latest: due=latest['next_date'] or due
                target='center-marketing-leads' if page=='leads' and 'crm' not in allowed else page
                add(page,r['id'],'跟进 · '+r['name'],target,r.get('project_id'),r['owner_id'],due,
                    ('marketing','crm') if page=='leads' else ('crm',),r.get('status',r.get('stage')),
                    note=(latest['next_action'] if latest else r.get('next_action')) or '')
        for row in db.execute("SELECT r.*,b.project_id,b.number FROM release_requests r JOIN order_baselines b ON b.id=r.baseline_id WHERE r.status='pending'"):
            r=dict(row)
            # Admin can supervise, but only CEO receives a decision in personal work.
            add('release',r['id'],'特殊放行 · '+r['number'],'releases',r['project_id'],None,
                scope=('engineering','crm','procurement'),status='待 CEO 审批',
                note=r['reason'],personal=user['role']=='ceo')
        for row in db.execute('SELECT * FROM engineering_tracking'):
            r=dict(row)
            if r['stage'] in ('售后','未来订单'): continue
            add('engineering',r['id'],'交付跟进 · '+projects.get(r['project_id'],{}).get('name',''),
                'center-engineering',r['project_id'],r['owner_id'],r['delivery_date'],
                ('engineering','factory'),r['stage'],bool(r['blocker_dept']),r['blocker_reason'] or r['issue'])
        if 'quote' in allowed:
            latest={}
            for raw in db.execute('SELECT * FROM quotation_history WHERE archived_at IS NULL AND voided_at IS NULL ORDER BY generated_at,id'):
                q=dict(raw)
                if q['project_id'] in projects: latest[q['project_id']]=q
            for pid,q in latest.items():
                if q.get('ordered_at'): continue
                owners=[e['id'] for e in employees.values() if e['email']==q['created_by'] and e['status']=='active']
                owner=owners[0] if len(owners)==1 else None
                add('quote',q['id'],('报价已确认，待下单 · ' if q['is_finalized'] else '报价待确认 · ')+projects[pid]['name'],
                    'orders' if q['is_finalized'] else 'quote-entry',pid,owner,scope=('quote','crm'),status='待下单' if q['is_finalized'] else '待确认报价')
        for row in db.execute('SELECT * FROM service_tickets'):
            r=dict(row)
            if r['project_id'] not in projects: continue
            import aftersales_dashboard
            payload=json.loads(r['payload'])
            if aftersales_dashboard.phase(payload)=='已关闭': continue
            # Legacy free-text names never become account assignments.
            owner=payload.get('ownerId') or payload.get('owner_id')
            if owner not in employees: owner=None
            shared=payload.get('workflowV10') or {}
            shared_scope=aftercare_sync.task_centers(shared) if shared else ['aftersales']
            add('service',r['id'],payload.get('description') or '售后事项','aftersales',
                r['project_id'],owner,aftersales_dashboard.local_date(payload.get('dueDate')),
                tuple(shared_scope),shared.get('stage') or aftersales_dashboard.phase(payload),
                payload.get('safetyLevel') in ('一般安全风险','S级安全问题'),
                ('原登记负责人：'+str(payload.get('owner'))+'；需核对账号分配') if not owner and payload.get('owner') else '',
                module_link='#ticket-detail/'+str(r['id']))
    if 'procurement' in allowed:
        for row in db.execute("SELECT p.*,x.project_id,u.email owner_email FROM purchase_orders p LEFT JOIN procurement_context x ON x.order_id=p.id LEFT JOIN users u ON u.id=p.created_by WHERE p.archived_at IS NULL AND p.status!='completed'"):
            r=dict(row)
            if not access.visible_order(db,user,r['id']): continue
            # Native accounts link to employees by verified login email, never display name.
            owners=[e['id'] for e in employees.values() if e['email']==r['owner_email'] and e['status']=='active']
            owner=owners[0] if len(owners)==1 else None
            if user['role']=='supplier': owner=user['id']
            totals=db.execute('SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(shipped_quantity),0),COALESCE(SUM(received_quantity),0),COALESCE(SUM(stocked_quantity),0) FROM order_items WHERE order_id=?',(r['id'],)).fetchone()
            if user['role']=='supplier' and totals[1]>=totals[0]: continue
            due=(r.get('promised_ship_date') or r.get('required_ship_date')) if totals[1]<totals[0] else None
            # Stock purchases have no project. Supplier scope is checked by visible_order above.
            pid=r['project_id']
            if user['role']=='supplier': pid=None
            add('purchase',r['id'],'采购跟进 · '+r['po_number'],'procurement',pid,owner,due,
                ('procurement','stock') if totals[2]<totals[0] or totals[3]<totals[0] else ('procurement',),
                r['status'],note=r.get('production_note') or '',
                module_link='&view=orders&order='+str(r['id']))

    # Dedup by authoritative record, then scope; no limit before counts are calculated.
    unique={item['id']:item for item in collected}
    rows=[item for item in unique.values() if not center or center in item['centers']]
    rank={'overdue':0,'today':1,'soon':2,'pending':3}
    rows.sort(key=lambda r:(rank[r['urgency']],not r['blocked'],r['due_date'] or '9999',r['id']))
    mine=[r for r in rows if r['mine']]
    attention=[r for r in rows if not r['mine'] and (managers and r['risk'] or not managers and center and (r['risk'] or r['status'] in ('待工程接收','待 CEO 审批')))]
    counts={key:sum(r['urgency']==key for r in mine) for key in rank}
    counts.update(total=len(mine),attention=len(attention))
    return {'today':today,'center':center,'project_id':project,'manager':managers,'counts':counts,
            'items':mine,'attention':attention,'available_centers':allowed,
            'notes':['按账号分配与现有项目权限汇总；姓名记录不自动视为账号分配。','业务处理沿用原页面；保存、切换页面或自动刷新后更新。']}
