"""Account-based project scope shared by the core and native workflow bridges."""

MANAGEMENT = ('admin', 'ceo')
STOCK_ROLES = ('purchasing', 'engineering', 'warehouse', 'finance')


def project_ids(db, user):
    if user['role'] in MANAGEMENT:
        return None
    if user['role'] == 'supplier':
        return []
    return [r[0] for r in db.execute('SELECT project_id FROM project_members WHERE employee_id=?', (user['id'],))]


def visible_project(db, user, project_id):
    return bool(project_id and (user['role'] in MANAGEMENT or (
        user['role'] != 'supplier' and db.execute(
            'SELECT 1 FROM project_members WHERE project_id=? AND employee_id=?',
            (project_id, user['id'])).fetchone())))


def visible_customer(db, user, customer_id):
    if user['role'] in MANAGEMENT:
        return True
    return user['role'] != 'supplier' and bool(db.execute('''SELECT 1 FROM customers c WHERE c.id=? AND
        (c.created_by=? OR EXISTS (SELECT 1 FROM projects p JOIN project_members m ON m.project_id=p.id
         WHERE p.customer_id=c.id AND m.employee_id=?))''', (customer_id, user['id'], user['id'])).fetchone())


def visible_order(db, user, order_id):
    record = db.execute('''SELECT p.supplier_id,c.project_id,c.purpose FROM purchase_orders p
        LEFT JOIN procurement_context c ON c.order_id=p.id WHERE p.id=?''', (order_id,)).fetchone()
    if not record:
        return False
    if user['role'] == 'supplier':
        return record['supplier_id'] == user.get('supplier_id')
    return (user['role'] in MANAGEMENT or visible_project(db, user, record['project_id']) or
            (record['purpose'] == 'stock' and user['role'] in STOCK_ROLES))


# Every supported identifier resolves to its authoritative parent, never a display name.
PROJECT_TABLES = {'projects', 'quotation_history', 'order_baselines', 'order_changes', 'service_tickets', 'deliveries'}
PARENTS = {
    'baseline_lines': ('baseline_id', 'order_baselines'),
    'release_requests': ('baseline_id', 'order_baselines'),
    'service_requests': ('ticket_id', 'service_tickets'),
    'delivery_lines': ('delivery_id', 'deliveries'),
    'customer_financial_entries': ('baseline_id', 'order_baselines'),
    'order_items': ('order_id', 'purchase_orders'),
    'warehouse_receipts': ('order_id', 'purchase_orders'),
    'warehouse_receipt_attachments': ('receipt_id', 'warehouse_receipts'),
    'attachments': ('order_id', 'purchase_orders'),
    'shipment_attachments': ('order_id', 'purchase_orders'),
    'shipment_quantity_corrections': ('order_id', 'purchase_orders'),
}


def visible_entity(db, user, entity, key):
    if entity == 'purchase_orders':
        return visible_order(db, user, key)
    if entity == 'customers':
        return visible_customer(db, user, key)
    if entity not in PROJECT_TABLES and entity not in PARENTS and entity not in ('stock_reservations', 'stock_movements'):
        return False
    record = db.execute(f'SELECT * FROM {entity} WHERE id=?', (key,)).fetchone()
    if not record:
        return False
    if entity in PROJECT_TABLES:
        if entity == 'quotation_history' and not record['project_id']:
            return user['role'] in MANAGEMENT  # Legacy records require verified project mapping.
        return visible_project(db, user, record['id'] if entity == 'projects' else record['project_id'])
    if entity in PARENTS:
        field, parent = PARENTS[entity]
        return visible_entity(db, user, parent, record[field])
    if record['ticket_id']:
        return visible_entity(db, user, 'service_tickets', record['ticket_id'])
    if entity == 'stock_reservations':
        return visible_entity(db, user, 'baseline_lines', record['baseline_line_id'])
    if record['order_item_id']:
        return visible_entity(db, user, 'order_items', record['order_item_id'])
    if record['reference_id']:
        return visible_entity(db, user, 'stock_reservations', record['reference_id'])
    return user['role'] in MANAGEMENT


def require(db, user, entity, key):
    from core import Problem, need
    if not visible_entity(db, user, entity, key):
        raise Problem('记录不存在或你已不在该项目中，请联系管理员核对项目成员', 404)
    return need(db, entity, key)


def members(db, project_id):
    return [dict(r) for r in db.execute('''SELECT m.employee_id,m.assignment_role,e.name,e.email,e.role,e.status
        FROM project_members m JOIN employees e ON e.id=m.employee_id WHERE m.project_id=?
        ORDER BY m.assignment_role DESC,e.name,e.email''', (project_id,))]


def assign(db, user, payload):
    from core import permit, need, Problem, now, audit
    permit(user, 'admin')
    project = need(db, 'projects', payload.get('project_id'))
    if payload.get('member_version') != project['member_version']:
        raise Problem('项目成员已被更新，请刷新后再保存', 409)
    ids = payload.get('employee_ids')
    owner = payload.get('owner_id') or None
    if not isinstance(ids, list) or any(not isinstance(key, str) for key in ids) or len(set(ids)) != len(ids):
        raise Problem('请重新选择项目成员')
    if owner and owner not in ids:
        raise Problem('项目负责人必须同时是项目成员')
    for key in ids:
        employee = need(db, 'employees', key)
        if employee['role'] == 'supplier' or employee['status'] != 'active':
            raise Problem('只能分配使用中的内部员工账号')
    before = members(db, project['id'])
    db.execute('DELETE FROM project_members WHERE project_id=?', (project['id'],))
    db.executemany('INSERT INTO project_members VALUES(?,?,?,?,?)',
                   [(project['id'], key, 'owner' if key == owner else 'member', user['id'], now()) for key in ids])
    db.execute('UPDATE projects SET member_version=member_version+1 WHERE id=?', (project['id'],))
    # Revoke selected project contexts without signing employees out of unrelated work.
    db.execute('''UPDATE employee_sessions SET project_id=NULL,quote_kind='original',parent_order_id=NULL
        WHERE project_id=? AND user_id NOT IN (SELECT employee_id FROM project_members WHERE project_id=?)
        AND user_id IN (SELECT id FROM employees WHERE role NOT IN ('admin','ceo'))''', (project['id'], project['id']))
    audit(db, user, 'project', project['id'], '分配项目成员', {'before': before, 'after': members(db, project['id'])})
    return {'ok': True, 'member_version': project['member_version'] + 1}


def guard_action(db, user, action, p):
    targets = {
        'order-from-quote': ('quotation_history', 'quote_id'),
        'request-release': ('order_baselines', 'baseline_id'),
        'confirm-deposit': ('order_baselines', 'baseline_id'),
        'change-create': ('baseline_lines', 'baseline_line_id'),
        'change-confirm': ('order_changes', 'id'), 'change-apply': ('order_changes', 'id'),
        'stock-cancel': ('stock_reservations', 'id'), 'stock-issue': ('stock_reservations', 'id'),
        'deliver': ('stock_reservations', 'id'), 'finance-entry': ('order_baselines', 'baseline_id'),
        'service-request': ('service_tickets', 'ticket_id'), 'technical-review': ('order_items', 'item_id'),
    }
    if action in targets:
        entity, field = targets[action]
        require(db, user, entity, p.get(field))
    if action == 'projects':
        require(db, user, 'customers', p.get('customer_id'))
    if action == 'master-update' and p.get('entity') in ('projects', 'customers'):
        require(db, user, p['entity'], p.get('id'))
    if action == 'create-po':
        if p.get('purpose') == 'project':
            require(db, user, 'order_baselines', p.get('baselineId'))
        if p.get('purpose') == 'service':
            require(db, user, 'service_requests', p.get('serviceRequestId'))
    if action == 'stock-reserve':
        if p.get('purpose') == 'delivery':
            require(db, user, 'baseline_lines', p.get('baseline_line_id'))
        if p.get('purpose') == 'service':
            require(db, user, 'service_tickets', p.get('ticket_id'))
