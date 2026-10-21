"""Android enrollment and telemetry. Device credentials never authorize staff APIs."""
import hashlib, json, re, secrets, time
import android_ops
import core as c
import centers, column_permissions as cp, project_access as access, runtime_config

DDL = [
'''CREATE TABLE IF NOT EXISTS android_products(id TEXT PRIMARY KEY,name TEXT NOT NULL,package_name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS android_enrollments(id TEXT PRIMARY KEY,code_hash TEXT NOT NULL UNIQUE,code_hint TEXT NOT NULL,product_id TEXT NOT NULL REFERENCES android_products(id),customer_id TEXT NOT NULL REFERENCES customers(id),site TEXT NOT NULL,label TEXT NOT NULL,expires REAL NOT NULL,state TEXT NOT NULL DEFAULT 'pending',device_id TEXT,created_by TEXT NOT NULL,created_at TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS android_devices(id TEXT PRIMARY KEY,installation_id TEXT NOT NULL UNIQUE,token_hash TEXT NOT NULL UNIQUE,enrollment_id TEXT NOT NULL UNIQUE REFERENCES android_enrollments(id),product_id TEXT NOT NULL REFERENCES android_products(id),customer_id TEXT NOT NULL REFERENCES customers(id),site TEXT NOT NULL,label TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',last_seen REAL,telemetry TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS android_bind_limits(peer_hash TEXT PRIMARY KEY,attempts INTEGER NOT NULL,expires REAL NOT NULL)''']

def init(db):
    for sql in DDL: db.execute(sql)

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def field(p,key,label,limit=200):return c.text(p.get(key),label,limit=limit)
def check(db,user,write=False):
    centers.require_center(db,user,'software');cp.require(db,user,'center-software',write)
    if write and user['role'] not in ('admin','ceo'):raise c.Problem('本阶段仅管理员与 CEO 可管理设备绑定',403)
def visible(db,user,customer):
    try:access.require(db,user,'customers',customer);return True
    except c.Problem:return False

def overview(db,user):
    check(db,user)
    customers=[dict(r) for r in db.execute('SELECT id,name FROM customers ORDER BY name') if visible(db,user,r['id'])]
    ids={r['id'] for r in customers};devices=[]
    for raw in db.execute('SELECT id,product_id,customer_id,site,label,state,last_seen,telemetry,created_at FROM android_devices ORDER BY created_at DESC'):
        d=dict(raw)
        if d['customer_id'] not in ids:continue
        d['telemetry']=json.loads(d['telemetry']);age=time.time()-(d['last_seen'] or 0)
        # JobScheduler is inexact in the background: stale is not proof of failure.
        d['connection']='revoked' if d['state']=='revoked' else 'online' if age<180 else 'recent' if age<1800 else 'offline'
        devices.append(d)
    enrollments=[dict(r) for r in db.execute('SELECT id,code_hint,product_id,customer_id,site,label,expires,state,device_id,created_at FROM android_enrollments ORDER BY created_at DESC') if r['customer_id'] in ids]
    for e in enrollments:
        if e['state']=='pending' and e['expires']<time.time():e['state']='expired'
    return {'products':[dict(r) for r in db.execute('SELECT * FROM android_products ORDER BY created_at DESC')], 'customers':customers,'devices':devices,'enrollments':enrollments,'can_write':not runtime_config.read_only(user) and user['role'] in ('admin','ceo') and cp.level(db,user,'center-software')==2,'server_time':time.time(),**android_ops.snapshot(db,user,ids)}

def action(db,user,name,p):
    check(db,user,True)
    if name=='resource':return android_ops.save(db,user,p)
    if name=='resource-state':return android_ops.change_state(db,user,p)
    if name=='task':return android_ops.task_create(db,user,p)
    if name=='task-action':return android_ops.task_action(db,user,p)
    if name=='product':
        label=field(p,'name','产品名称',100);package=field(p,'package_name','安卓包名',200)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',package):raise c.Problem('包名格式不正确，例如 com.company.dart')
        if db.execute('SELECT 1 FROM android_products WHERE package_name=?',(package,)).fetchone():raise c.Problem('此包名已登记',409)
        key=c.uid();db.execute('INSERT INTO android_products VALUES(?,?,?,?)',(key,label,package,c.now()));c.audit(db,user,'android_product',key,'登记安卓产品',{'package_name':package});return {'ok':True}
    if name=='license':
        product=c.need(db,'android_products',p.get('product_id'));customer=c.need(db,'customers',p.get('customer_id'));access.require(db,user,'customers',customer['id'])
        if p.get('site_id'):
            place=android_ops.active(db,p['site_id'],'site')
            if place['customer_id']!=customer['id']:raise c.Problem('场地与客户不一致')
            p={**p,'site':place['data']['name']}
        site=field(p,'site','场地',100);label=field(p,'label','设备名称',100);raw='AND-'+secrets.token_hex(16).upper();key=c.uid()
        db.execute('INSERT INTO android_enrollments(id,code_hash,code_hint,product_id,customer_id,site,label,expires,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,digest(raw),raw[-6:],product['id'],customer['id'],site,label,time.time()+7*86400,user['id'],c.now()))
        c.audit(db,user,'android_enrollment',key,'签发安卓绑定码',{'customer_id':customer['id'],'site':site});return {'ok':True,'code':raw,'expires_in_days':7}
    if name=='revoke':
        key=field(p,'id','记录编号',100);kind=p.get('kind')
        if kind not in ('enrollment','device'):raise c.Problem('记录类型不正确')
        table='android_enrollments' if kind=='enrollment' else 'android_devices';record=c.need(db,table,key);access.require(db,user,'customers',record['customer_id'])
        db.execute('UPDATE '+table+" SET state='revoked' WHERE id=?",(key,))
        if kind=='enrollment':db.execute("UPDATE android_devices SET state='revoked' WHERE enrollment_id=?",(key,))
        else:db.execute("UPDATE android_enrollments SET state='revoked' WHERE id=?",(record['enrollment_id'],))
        c.audit(db,user,'android_'+kind,key,'撤销安卓绑定',{});return {'ok':True}
    raise c.Problem('接口不存在',404)

def report(p):
    raw=p.get('telemetry',{})
    if not isinstance(raw,dict):raise c.Problem('设备状态格式不正确')
    allowed=('manufacturer','model','android_version','sdk_int','agent_version','app_version','app_version_code','device_owner','managed_install','reboot','package_name','protocol_version','supported_tasks')
    result={}
    for key in allowed:
        value=raw.get(key)
        if value is None:continue
        if key=='supported_tasks':
            if not isinstance(value,list) or len(value)>20 or any(v not in android_ops.TASKS for v in value):raise c.Problem('任务能力清单无效')
            result[key]=list(dict.fromkeys(value));continue
        if key in ('device_owner','managed_install','reboot'):
            if type(value) is not bool:raise c.Problem('设备能力格式不正确')
        elif key in ('sdk_int','app_version_code','protocol_version'):
            if type(value) is not int or not 0<=value<=2147483647:raise c.Problem('设备版本格式不正确')
        elif not isinstance(value,str) or len(value)>200:raise c.Problem('设备信息格式不正确')
        result[key]=value
    return result

def agent(db,name,p,authorization='',peer=''):
    if name=='sync':return android_ops.sync(db,p,authorization)
    if name=='bind':
        peer_hash=digest(peer);stamp=time.time();limit=c.row(db,'SELECT * FROM android_bind_limits WHERE peer_hash=?',(peer_hash,))
        if limit and limit['expires']>stamp and limit['attempts']>=30:raise c.Problem('绑定请求过于频繁，请稍后重试',429)
        db.execute('DELETE FROM android_bind_limits WHERE expires<?',(stamp,))
        db.execute('INSERT INTO android_bind_limits VALUES(?,1,?) ON CONFLICT(peer_hash) DO UPDATE SET attempts=attempts+1',(peer_hash,stamp+900))
        # Commit attempts independently, including failed bindings; no caller secrets are retained.
        db.commit()
        raw=field(p,'code','绑定码',100).upper();install=field(p,'installation_id','安装编号',100);token=field(p,'device_secret','设备凭证',100)
        if not re.fullmatch(r'[A-Za-z0-9_-]{43,100}',token):raise c.Problem('设备凭证格式不正确')
        e=c.row(db,'SELECT * FROM android_enrollments WHERE code_hash=?',(digest(raw),));existing=c.row(db,'SELECT * FROM android_devices WHERE installation_id=?',(install,))
        if e and existing and e['state']=='bound' and existing['enrollment_id']==e['id'] and existing['state']=='active' and secrets.compare_digest(existing['token_hash'],digest(token)):
            return {'ok':True,'device_id':existing['id'],'package_name':c.need(db,'android_products',e['product_id'])['package_name']}
        if not e or e['state']!='pending' or e['expires']<stamp:raise c.Problem('绑定码无效、过期或已使用',403)
        if existing:raise c.Problem('此安装已绑定，请联系管理员处理',409)
        telemetry=report(p);key=c.uid();package=c.need(db,'android_products',e['product_id'])['package_name']
        db.execute('INSERT INTO android_devices(id,installation_id,token_hash,enrollment_id,product_id,customer_id,site,label,last_seen,telemetry,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,install,digest(token),e['id'],e['product_id'],e['customer_id'],e['site'],e['label'],stamp,json.dumps(telemetry),c.now()))
        db.execute("UPDATE android_enrollments SET state='bound',device_id=? WHERE id=? AND state='pending'",(key,e['id']))
        return {'ok':True,'device_id':key,'package_name':package}
    if name=='heartbeat':
        token=authorization.removeprefix('Bearer ')
        if not authorization.startswith('Bearer ') or len(token)>100:raise c.Problem('设备凭证无效',401)
        d=c.row(db,"SELECT * FROM android_devices WHERE token_hash=? AND state='active'",(digest(token),))
        if not d:raise c.Problem('设备凭证失效或设备已撤销',401)
        telemetry=report(p);package=c.need(db,'android_products',d['product_id'])['package_name']
        if telemetry.get('package_name')!=package:raise c.Problem('上报包名与绑定产品不一致')
        db.execute('UPDATE android_devices SET last_seen=?,telemetry=? WHERE id=?',(time.time(),json.dumps(telemetry),d['id']))
        return {'ok':True,'device_id':d['id'],'server_time':time.time()}
    raise c.Problem('接口不存在',404)
