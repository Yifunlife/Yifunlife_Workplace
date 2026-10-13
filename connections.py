"""Source-owned sales/catalog records, linked by stable IDs without merging names."""
import hashlib
import json
import logging
import threading
import urllib.parse
import urllib.request
from pathlib import Path
import core as c
import database
import project_access as access

ORIGIN = 'https://yifunlife-erp.yifunlife.workers.dev'
_lock = threading.Lock()


def configuration():
    path = database.DB_PATH.parent / 'connections.json'
    return json.loads(path.read_text()) if path.exists() else {}


def stable_id(kind, source_id):
    return kind + '-' + hashlib.sha256(source_id.encode()).hexdigest()[:32]


def sync_sales(db, clients, actor):
    if not isinstance(clients, list) or len(clients) > 50000:
        raise ValueError('销售客户列表格式不正确')
    seen = set()
    for item in clients:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or item['id'] in seen:
            raise ValueError('销售客户编号缺失或重复，已停止同步')
        if not isinstance(item.get('name'), str) or not item['name'].strip():
            raise ValueError('销售客户名称缺失，已停止同步')
        seen.add(item['id'])
    stamp = c.now()
    db.execute('UPDATE connected_sales SET active=0')
    count = 0
    for item in clients:
        old = c.row(db, 'SELECT * FROM connected_sales WHERE source_id=?', (item['id'],))
        if item.get('deleted'):
            continue
        count += 1
        customer_id = old['customer_id'] if old else stable_id('sales-customer', item['id'])
        project_id = old['project_id'] if old else None
        fields = (item['name'].strip(), item.get('whatsapp') or '', item.get('email') or '')
        if not old:
            db.execute('INSERT INTO customers(id,code,name,phone,email,created_at,created_by) VALUES(?,?,?,?,?,?,?)',
                       (customer_id, 'SALES-' + item['id'], *fields, stamp, actor['id']))
        else:
            db.execute('UPDATE customers SET name=?,phone=?,email=?,version=version+1 WHERE id=? AND (name!=? OR phone!=? OR email!=?)',
                       (*fields, customer_id, *fields))
        name = str(item.get('project') or '').strip()
        if name and not project_id:
            project_id = stable_id('sales-project', item['id'])
            db.execute('INSERT INTO projects(id,code,name,customer_id,location,notes,created_at) VALUES(?,?,?,?,?,?,?)',
                       (project_id, 'SALES-' + item['id'], name, customer_id, str(item.get('country') or ''), '来源：亦玩销售工作台；负责人须在人员与权限中分配。', stamp))
        elif name and project_id:
            db.execute('UPDATE projects SET name=?,version=version+1 WHERE id=? AND name!=?', (name, project_id, name))
        # Only operational customer fields cross into Workplace; conversations and drafts stay in the sales app.
        payload = json.dumps({key: item.get(key) for key in ('id','name','country','project','grade','stage','projectStatus','whatsapp','email','source','customerType','nextAction','nextContact','followStatus','owner','lastContact')}, ensure_ascii=False)
        db.execute('INSERT INTO connected_sales VALUES(?,?,?,?,1,?) ON CONFLICT(source_id) DO UPDATE SET project_id=excluded.project_id,payload=excluded.payload,active=1,synced_at=excluded.synced_at',
                   (item['id'], customer_id, project_id, payload, stamp))
    return count


def remote(config, path, payload=None):
    if config.get('quote_origin') != ORIGIN:
        raise ValueError('报价网站地址与已确认的数据源不一致')
    request = urllib.request.Request(ORIGIN + path, data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + config['quote_token'], 'Content-Type': 'application/json',
                 'User-Agent': 'Yifun-Workplace/1.0', 'Accept': 'application/json'})
    # Never forward the connector credential to a redirect target.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        return json.load(response)


def remote_records(config, kind):
    items = []; after = ''; seen = set()
    while True:
        page = remote(config, '/api/workplace-sync?kind=' + kind + '&after=' + urllib.parse.quote(after))
        if not isinstance(page.get('items'), list): raise ValueError('报价网站返回的资料格式不正确')
        items.extend(page['items'])
        after = page.get('next')
        if not after: return items
        if after in seen or len(items) > 100000: raise ValueError('报价网站分页异常，已停止同步')
        seen.add(after)


def project_payload(db):
    return [{'id': p['id'], 'name': p['name'], 'customer_name': p['customer_name'],
             'allowed_emails': [r[0].lower() for r in db.execute("SELECT e.email FROM project_members m JOIN employees e ON e.id=m.employee_id WHERE m.project_id=? AND e.status='active' AND e.role='sales'", (p['id'],))]}
            for p in db.execute("SELECT p.id,p.name,c.name customer_name FROM projects p JOIN customers c ON c.id=p.customer_id WHERE p.status='active'")]


def sync_quote(db, products, quotes):
    stamp = c.now()
    db.execute("UPDATE products SET source='online_quote_archived' WHERE source='online_quote'")
    for p in products:
        key = 'online:' + p['id']
        db.execute('''INSERT INTO products(id,sku,name,english_name,specification,unit,image_key,source,created_at)
            VALUES(?,?,?,?,?,?,?,'online_quote',?) ON CONFLICT(id) DO UPDATE SET sku=excluded.sku,name=excluded.name,
            english_name=excluded.english_name,specification=excluded.specification,unit=excluded.unit,image_key=excluded.image_key,source='online_quote' ''',
            (key, p['sku'], p['name'], p.get('english_name') or '', p.get('specification') or '', p.get('unit') or '', p.get('image_key') or '', stamp))
    for q in quotes:
        payload = json.dumps(q, ensure_ascii=False, sort_keys=True)
        old = c.row(db, 'SELECT * FROM connected_quotes WHERE id=?', (q['id'],))
        remote_project = q.get('workspace_project_id')
        if remote_project and not c.row(db, 'SELECT id FROM projects WHERE id=?', (remote_project,)):
            remote_project = None
        project_id = old['project_id'] if old else remote_project
        if old and old['project_id'] and remote_project and old['project_id'] != remote_project:
            raise ValueError('报价项目关联冲突，已停止同步，请核对原始报价')
        project_id = project_id or remote_project
        db.execute('''INSERT INTO connected_quotes VALUES(?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET
            project_id=excluded.project_id,payload=excluded.payload,synced_at=excluded.synced_at,
            version=connected_quotes.version+CASE WHEN connected_quotes.payload!=excluded.payload OR connected_quotes.project_id IS NOT excluded.project_id THEN 1 ELSE 0 END''',
            (q['id'], project_id, payload, stamp))
    return len(quotes)


def run_source(name, callback):
    try:
        count = callback()
        with database.connect() as db:
            db.execute('INSERT INTO connection_runs VALUES(?,?,?,\'\',?) ON CONFLICT(source) DO UPDATE SET last_success=excluded.last_success,last_attempt=excluded.last_attempt,error=\'\',count=excluded.count', (name, c.now(), c.now(), count))
    except Exception as error:
        # Avoid logging credentials, response bodies, or customer data.
        message = str(error) if isinstance(error, ValueError) else '连接未完成，请检查网络、原应用资料和连接配置后重试。'
        with database.connect() as db:
            db.execute('INSERT INTO connection_runs(source,last_attempt,error) VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,error=excluded.error', (name, c.now(), message))
        logging.warning('Connection %s failed (%s)', name, type(error).__name__)


def sync():
    if not _lock.acquire(blocking=False): return
    try:
        config = configuration()
        if not config.get('enabled'): return
        with database.connect() as db:
            actor = c.need(db, 'employees', config['actor_id'])
            if actor['role'] != 'admin' or actor['status'] != 'active': raise ValueError('连接负责人须为有效管理员')
        def sales():
            path = Path(config['sales_workspace']) / '.workbench/crm.json'
            data = json.loads(path.read_text())
            with database.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                return sync_sales(db, data['clients'], actor)
        run_source('sales', sales)
        if config.get('quote_token'):
            def quote():
                products = remote_records(config, 'products'); quotes = remote_records(config, 'quotations')
                with database.connect() as db: projects = project_payload(db)
                remote(config, '/api/workplace-sync', {'projects': projects})
                with database.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    return sync_quote(db, products, quotes)
            run_source('quote', quote)
    finally: _lock.release()


def start():
    if not configuration().get('enabled'): return
    def loop():
        while True:
            try: sync()
            except Exception as error: logging.warning('Connection worker failed (%s)', type(error).__name__)
            threading.Event().wait(60)
    threading.Thread(target=loop, name='workplace-connections', daemon=True).start()


def status(db, user, project=None):
    c.permit(user, 'admin', 'ceo', 'sales', 'engineering')
    if project: access.require(db, user, 'projects', project)
    config = configuration()
    sales = []
    for r in db.execute('SELECT * FROM connected_sales WHERE active=1 ORDER BY source_id'):
        if not access.visible_customer(db, user, r['customer_id']) or (project and r['project_id'] != project): continue
        sales.append({**json.loads(r['payload']), 'customer_id': r['customer_id'], 'project_id': r['project_id']})
    quotes = []
    if user['role'] in ('admin','ceo','sales','engineering'):
        for r in db.execute('SELECT * FROM connected_quotes ORDER BY synced_at DESC,id'):
            if project and r['project_id'] != project: continue
            if user['role'] not in ('admin','ceo') and not access.visible_project(db, user, r['project_id']): continue
            value=json.loads(r['payload'])
            if user['role']=='engineering':
                value={k:v for k,v in value.items() if k not in ('final_amount','final_currency','created_by')}
            quotes.append({**value, 'project_id': r['project_id'], 'version': r['version']})
    return {'enabled': bool(config.get('enabled')), 'quote_url': ORIGIN if config.get('quote_token') else None,
            'runs': [dict(r) for r in db.execute('SELECT * FROM connection_runs')] if user['role'] in ('admin','ceo') else [],
            'products': db.execute("SELECT COUNT(*) FROM products WHERE source='online_quote'").fetchone()[0],
            'sales': sales, 'quotes': quotes, 'can_manage': user['role']=='admin'}


def action(db, user, name, p):
    c.permit(user, 'admin')
    if name == 'link':
        old = c.need(db, 'connected_quotes', p.get('id'))
        if old['version'] != p.get('version'): raise c.Problem('报价已更新，请刷新', 409)
        if old['project_id']: raise c.Problem('已有项目关联不能覆盖，请核对原始资料')
        project = access.require(db, user, 'projects', p.get('project_id'))
        db.execute('UPDATE connected_quotes SET project_id=?,version=version+1 WHERE id=?', (project['id'], old['id']))
        c.audit(db, user, 'connected_quote', old['id'], '关联线上报价项目', {'project_id': project['id']})
        return {'ok': True}
    raise c.Problem('连接操作不存在', 404)
