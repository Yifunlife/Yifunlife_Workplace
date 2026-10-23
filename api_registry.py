"""Administrator-owned API configuration. Saving never sends a request."""
import json
import re
from urllib.parse import urlsplit
import core as c


def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS api_registry(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
        method TEXT NOT NULL, headers TEXT NOT NULL, body TEXT NOT NULL,
        notes TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)''')


def listing(db, user):
    c.permit(user, 'admin')
    rows = []
    for row in db.execute('SELECT * FROM api_registry ORDER BY updated_at DESC,id'):
        item = dict(row)
        item['has_headers'] = bool(json.loads(item.pop('headers')))
        rows.append(item)
    return {'items': rows}


def action(db, user, operation, p):
    c.permit(user, 'admin')
    if operation not in ('save', 'delete'):
        raise c.Problem('接口不存在', 404)
    old = c.need(db, 'api_registry', p['id']) if p.get('id') else None
    if old and p.get('version') != old['version']:
        raise c.Problem('配置已被修改，请刷新后重试', 409)
    if operation == 'delete':
        if not old:
            raise c.Problem('请选择要删除的接口')
        db.execute('DELETE FROM api_registry WHERE id=?', (old['id'],))
        c.audit(db, user, 'api_registry', old['id'], '删除 API 接口', {'name': old['name']})
        return {'ok': True}
    name = c.text(p.get('name'), '接口名称', limit=100)
    url = c.text(p.get('url'), '接口地址', limit=2000)
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment
        parsed.port
    except ValueError:
        valid = False
    if not valid or any(ch.isspace() for ch in url):
        raise c.Problem('请填写有效的 HTTPS 接口地址，不包含账号密码或片段')
    method = p.get('method')
    if method not in ('GET', 'POST'):
        raise c.Problem('请选择 GET 或 POST')
    notes = c.text(p.get('notes', ''), '用途说明', required=False, limit=2000)
    body = c.text(p.get('body', ''), '请求参数', required=False, limit=16000)
    if body:
        try:
            json.loads(body)
        except ValueError:
            raise c.Problem('请求参数必须是有效的 JSON')
    if method == 'GET' and body:
        raise c.Problem('GET 的查询参数请放在接口地址中，请清空请求参数')
    raw = c.text(p.get('headers', ''), '请求头', required=False, limit=16000)
    if raw:
        try:
            headers = json.loads(raw)
        except ValueError:
            raise c.Problem('请求头必须是 JSON 对象')
        if not isinstance(headers, dict) or any(not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", k) or not isinstance(v, str) or '\r' in v or '\n' in v for k, v in headers.items()):
            raise c.Problem('请求头须为名称与文本值组成的 JSON 对象')
    else:
        headers = json.loads(old['headers']) if old else {}
    key = old['id'] if old else c.uid()
    values = (name, url, method, json.dumps(headers), body, notes, c.now())
    if old:
        db.execute('UPDATE api_registry SET name=?,url=?,method=?,headers=?,body=?,notes=?,updated_at=?,version=version+1 WHERE id=?', (*values, key))
    else:
        db.execute('INSERT INTO api_registry(id,name,url,method,headers,body,notes,updated_at) VALUES(?,?,?,?,?,?,?,?)', (key, *values))
    c.audit(db, user, 'api_registry', key, '保存 API 接口', {'name': name, 'method': method})
    return {'ok': True, 'id': key}
