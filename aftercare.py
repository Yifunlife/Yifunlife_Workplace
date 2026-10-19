"""V10 after-sales workflow inside Workplace's auth, project scope and durable store.
The imported JS handler runs against a scoped transient SQLite snapshot. Only its
parameterized writes to namespaced after-sales tables are replayed in the caller's
transaction; no account database or filesystem persistence is imported.
"""
import base64,hashlib,json,os,re,shutil,subprocess,time,uuid
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import core,project_access as access,runtime_config,object_storage
ROOT=Path(__file__).resolve().parent
HOME=ROOT/'aftercare'
TABLES=('customer_profiles','customer_stores','customer_invites','customer_requests','customer_work_items','customer_files','customer_rate_limits','account_audit')
ROLES={'admin':'管理员','ceo':'负责人','aftersales':'售后专员','engineering':'工程人员','purchasing':'采购人员','warehouse':'仓库人员','installation':'安装人员','finance':'财务人员','sales':'负责人'}
TRANSITIONS={'登记草稿':{'登记草稿','审核'},'审核':{'审核','部门处理','工程下单','生产采购','采购','生产','现场处理','发货物流','客户验收'},'部门处理':{'部门处理','工程下单','生产采购','采购','生产','现场处理','发货物流','客户验收','审核'},'工程下单':{'工程下单','生产采购','采购','生产','现场处理','发货物流','审核'},'生产采购':{'生产采购','品质检验','发货物流','审核'},'采购':{'采购','品质检验','发货物流','审核'},'生产':{'生产','品质检验','发货物流','审核'},'品质检验':{'品质检验','发货物流','生产采购','审核'},'发货物流':{'发货物流','现场处理','客户验收','审核'},'现场处理':{'现场处理','客户验收','审核'},'客户验收':{'客户验收','负责人复核','现场处理'},'负责人复核':{'负责人复核','已关闭','客户验收'},'已关闭':{'已关闭'}}

def role(db,user):
    if user['role']=='engineering' and db.execute("SELECT 1 FROM center_members WHERE employee_id=? AND center='factory'",(user['id'],)).fetchone():return '生产人员'
    if user['role']=='engineering' and db.execute("SELECT 1 FROM center_members WHERE employee_id=? AND center='aftersales'",(user['id'],)).fetchone():return '审核人员'
    return ROLES.get(user['role'],'负责人')

def profile(db,user):
    if not user:return None
    return {'id':user['id'],'name':user['name'],'email':user['email'],'role':'负责人' if runtime_config.read_only(user) else role(db,user),'active':user['status']=='active','must_change':False,'mustChange':False}

def projects(db,user):
    return [dict(r) for r in db.execute('SELECT p.id,p.name,p.customer_id,p.location,c.name customer,c.contact,c.phone,c.email FROM projects p JOIN customers c ON c.id=p.customer_id ORDER BY p.name') if access.visible_project(db,user,r['id'])]

def bootstrap(db,user):
    if not user:raise core.Problem('请先登录统一工作平台',401)
    p=projects(db,user)
    team=[{'id':r['id'],'name':r['name'],'role':role(db,dict(r))} for r in db.execute("SELECT id,name,role,status,email FROM employees WHERE status='active'")]
    context={'user':profile(db,user),'projects':p,'team':team,'csrf':user['csrf'],'readOnly':runtime_config.read_only(user)}
    return ('window.__AFTERCARE_CONTEXT__='+json.dumps(context,ensure_ascii=False).replace('<','\\u003c')+';window.__EMPLOYEE__=window.__AFTERCARE_CONTEXT__.user;').encode()

def tables_exist(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='af2_customer_work_items'").fetchone())

def seed_legacy(db):
    """Copy existing tickets once, retaining their ID and their authoritative project."""
    for r in db.execute('SELECT t.*,p.name project_name,c.name customer_name FROM service_tickets t JOIN projects p ON p.id=t.project_id JOIN customers c ON c.id=p.customer_id').fetchall():
        existing=db.execute('SELECT * FROM af2_customer_work_items WHERE id=?',(r['id'],)).fetchone()
        if existing:
            link=db.execute('SELECT core_version FROM af2_ticket_links WHERE ticket_id=?',(r['id'],)).fetchone()
            if link and link['core_version']==r['version']:continue
            p=json.loads(r['payload']);d=json.loads(existing['payload'])
            import aftersales_dashboard
            incoming=aftersales_dashboard.phase(p)
            previous={'采购':'生产采购','生产':'生产采购','品质检验':'生产采购','部门处理':'现场处理','负责人复核':'客户验收'}.get(d.get('stage'),d.get('stage'))
            if incoming!=previous and incoming in TRANSITIONS:d['stage']=incoming
            for key,field in [('product','product'),('issue','description'),('reported','date'),('delivered','deliveryDate'),('issueType','category'),('problemType','problemType'),('owner','owner'),('planned','dueDate'),('feedback','notes'),('method','executionMethod'),('grade','safetyLevel'),('cost','costResponsibility'),('model','model'),('region','region'),('deviceId','deviceId'),('faultDate','faultDate'),('activationDate','activationDate'),('lastRepairCompletedDate','lastRepairCompletedDate'),('rootCause','rootCause'),('rootCauseStatus','rootCauseStatus'),('rootCauseEvidence','rootCauseEvidence'),('correctiveAction','correctiveAction'),('validationResult','validationResult'),('validationStatus','validationStatus'),('problemPart','problemPart')]:
                if field in p:d[key]=p[field]
            d['legacyVersion']=r['version']
            db.execute('UPDATE af2_customer_work_items SET payload=?,version=version+1,updated_at=? WHERE id=?',(json.dumps(d,ensure_ascii=False),int(time.time()*1000),r['id']))
            db.execute('INSERT INTO af2_ticket_links VALUES(?,?) ON CONFLICT(ticket_id) DO UPDATE SET core_version=excluded.core_version',(r['id'],r['version']))
            continue
        import aftersales_dashboard
        p=json.loads(r['payload']);stage=aftersales_dashboard.phase(p)
        if stage not in TRANSITIONS:stage='审核'
        d={'id':r['id'],'projectId':r['project_id'],'project':r['project_name'],'customer':r['customer_name'],'order':p.get('order',''),'product':p.get('product',''),'issue':p.get('description',''),'reported':p.get('date') or r['created_at'][:10],'delivered':p.get('deliveryDate',''),'issueType':p.get('category') or p.get('problemType','待分类'),'cause':p.get('causeCategory','待确认'),'grade':p.get('safetyLevel','待评估'),'owner':p.get('owner',''),'trackingOwner':p.get('owner',''),'feedback':p.get('notes',''),'method':p.get('executionMethod','待确定'),'cost':p.get('costResponsibility','待确认'),'planned':p.get('dueDate',''),'actual':'','stage':stage,'stageEnteredAt':r['updated_at'][:10],'history':p.get('history',[]),'attachments':[],'source':'原售后记录','submitted':True,'batchId':'LEGACY-'+r['id'],'workNo':r['id'],'country':p.get('region',''),'legacyVersion':r['version']}
        for key in ('deviceId','model','region','faultDate','activationDate','lastRepairCompletedDate','rootCause','rootCauseStatus','rootCauseEvidence','correctiveAction','validationResult','validationStatus','problemPart','problemType'):
            d[key]=p.get(key,'')
        request_id=internal_request(db,r['project_id'],r['created_by'])
        db.execute('INSERT OR IGNORE INTO af2_customer_work_items VALUES(?,?,?,1,?,?)',(r['id'],request_id,json.dumps(d,ensure_ascii=False),int(time.time()*1000),r['created_by']))
        db.execute('INSERT INTO af2_ticket_links VALUES(?,?) ON CONFLICT(ticket_id) DO NOTHING',(r['id'],r['version']))

def internal_request(db,pid,actor):
    rid='INTERNAL-'+pid
    if db.execute('SELECT 1 FROM af2_customer_requests WHERE id=?',(rid,)).fetchone():return rid
    p=core.need(db,'projects',pid);c=core.need(db,'customers',p['customer_id']);cid='CORE-'+c['id'];sid='CORE-'+pid;now=int(time.time()*1000)
    db.execute('INSERT OR IGNORE INTO af2_customer_profiles VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,c['id'],c['name'],c.get('contact') or '',c.get('email') or '',c.get('phone') or '',p.get('location') or '','zh','',now))
    db.execute('INSERT OR IGNORE INTO af2_customer_stores VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,cid,pid,p['name'],pid,p.get('location') or '',c.get('contact') or '',c.get('email') or '',c.get('phone') or '',now))
    iid='INTERNAL-'+pid
    db.execute('INSERT OR IGNORE INTO af2_customer_invites VALUES(?,?,?,0,0,?,?)',(iid,cid,hashlib.sha256(iid.encode()).hexdigest(),actor,now))
    payload={'storeId':sid,'project':p['name'],'order':pid,'issues':[],'contact':c.get('contact') or '','email':c.get('email') or '','phone':c.get('phone') or '','address':p.get('location') or ''}
    db.execute('INSERT OR IGNORE INTO af2_customer_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,cid,sid,iid,rid,'internal',json.dumps(payload,ensure_ascii=False),'',None,None,now,now))
    return rid

def visible_sets(db,user):
    all_access=user and user['role'] in ('admin','ceo')
    pids={p['id'] for p in projects(db,user)} if user else set()
    owned={r['id'] for r in db.execute('SELECT id FROM af2_ownership WHERE owner_id=?',(user['id'],))} if user else set()
    stores={r['id'] for r in db.execute('SELECT id,market_id FROM af2_customer_stores') if all_access or r['market_id'] in pids or r['id'] in owned}
    customers={r['customer_id'] for r in db.execute('SELECT id,customer_id FROM af2_customer_stores') if r['id'] in stores}
    customers|=owned
    requests={r['id'] for r in db.execute('SELECT id,store_id FROM af2_customer_requests') if all_access or r['store_id'] in stores}
    return all_access,pids,stores,customers,requests

def snapshot(db,user):
    all_access,pids,stores,customers,requests=visible_sets(db,user) if user else (True,set(),set(),set(),set())
    out=[]
    for name in TABLES:
        table='af2_'+name;schema=db.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()[0]
        schema=re.sub(r'\baf2_([a-z_]+)\b',r'\1',schema)
        columns=[r['name'] for r in db.execute('PRAGMA table_info('+table+')')]
        rows=[]
        for raw in db.execute('SELECT * FROM '+table):
            r=dict(raw)
            if not all_access:
                if name=='customer_profiles' and r['id'] not in customers:continue
                if name=='customer_stores' and r['id'] not in stores:continue
                if name=='customer_invites' and r['customer_id'] not in customers:continue
                if name=='customer_requests' and r['id'] not in requests:continue
                if name in ('customer_work_items','customer_files') and r['request_id'] not in requests:continue
                if name=='account_audit' and r['actor']!=user['id']:continue
            rows.append([r[c] for c in columns])
        out.append({'name':name,'sql':schema,'columns':columns,'rows':rows})
    employees=[dict(r) for r in db.execute("SELECT id,name,role,status,email FROM employees WHERE status='active'")]
    out.append({'name':'employees','sql':'CREATE TABLE employees(id TEXT,name TEXT,role TEXT,active INTEGER,must_change INTEGER)','columns':['id','name','role','active','must_change'],'rows':[[r['id'],r['name'],role(db,r),1,0] for r in employees]})
    return out

def validate_item(db,user,item,old=None):
    if not isinstance(item,dict) or len(json.dumps(item))>90000:raise core.Problem('工单内容过长或格式不正确')
    pid=(old or {}).get('projectId') or item.get('projectId')
    access.require(db,user,'projects',pid)
    if old and item.get('projectId',pid)!=pid:raise core.Problem('不能更换已建工单的关联项目',403)
    if old and item.get('stage') not in TRANSITIONS.get(old.get('stage'),{old.get('stage')}):raise core.Problem('不能跳过售后处理环节，请按当前阶段办理',409)
    for key in ('reported','delivered','planned','actual','faultDate','activationDate','lastRepairCompletedDate'):
        if item.get(key):
            from datetime import date
            try:date.fromisoformat(item[key])
            except (ValueError,TypeError):raise core.Problem('请填写有效日期')
    if item.get('faultDate') and item.get('delivered') and item['faultDate']<item['delivered']:raise core.Problem('故障日期不能早于设备交付日期')
    if item.get('deviceId'):
        asset=db.execute('SELECT project_id FROM equipment_assets WHERE serial=?',(item['deviceId'],)).fetchone()
        if asset and asset['project_id']!=pid:raise core.Problem('该设备编号属于其他项目，请核对',403)
    if item.get('rootCauseStatus') in ('confirmed','已验证') and (not item.get('rootCauseEvidence') or not item.get('rootCause')):raise core.Problem('确认根因需要填写根因和验证依据')
    if item.get('stage')=='已关闭' and old and old.get('stage')!='负责人复核':raise core.Problem('工单须经过负责人复核才能关闭')
    if old and user['role']!='admin':
        r=role(db,user)
        protected={'售后专员':('review','reviewDraft','engineering','production','purchase','shipment'), '审核人员':('engineering','production','purchase','shipment'), '工程人员':('review','production','purchase','shipment'), '生产人员':('review','engineering','purchase','shipment'), '采购人员':('review','engineering','production','shipment'), '仓库人员':('review','engineering','production','purchase'), '安装人员':('review','engineering','production','purchase','shipment')}.get(r,())
        if any(item.get(k)!=old.get(k) for k in protected):raise core.Problem('不能修改其他岗位的处理记录',403)
        if r=='售后专员' and old.get('stage')=='审核' and item.get('stage')!='审核':raise core.Problem('待审核工单需要审核员处理',403)
    if old and user['role']!='admin':
        immutable=('customer','project','order','batchId','source','workNo','projectId')
        if any(item.get(k,old.get(k))!=old.get(k) for k in immutable):raise core.Problem('不能更改工单归属',403)
    return pid

def internal_save(db,user,b):
    items=b.get('items')
    if not isinstance(items,list) or len(items)!=1:raise core.Problem('每次保存一条工单')
    item=items[0];existing=db.execute('SELECT * FROM af2_customer_work_items WHERE id=?',(item.get('id'),)).fetchone()
    if existing:return None
    if role(db,user) not in ('管理员','售后专员'):raise core.Problem('仅售后专员可以登记新工单',403)
    pid=validate_item(db,user,item)
    if not item.get('product') or not item.get('issue') or not item.get('owner'):raise core.Problem('请补齐产品、问题描述和负责人')
    if item.get('stage') not in ('登记草稿','审核'):raise core.Problem('新工单必须从登记或审核开始')
    if not isinstance(item.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',item['id']):raise core.Problem('工单编号无效')
    p=core.need(db,'projects',pid);c=core.need(db,'customers',p['customer_id'])
    item={**item,'projectId':pid,'project':p['name'],'customer':c['name'],'attachments':[],'source':item.get('source') if item.get('source') in ('手动填写','表格导入') else '内部登记 / Excel导入'}
    item.pop('cloudVersion',None);rid=internal_request(db,pid,user['id']);item['cloudRequestId']=rid
    db.execute('INSERT OR IGNORE INTO af2_customer_work_items VALUES(?,?,?,1,?,?)',(item['id'],rid,json.dumps(item,ensure_ascii=False),int(time.time()*1000),user['id']))
    sync_ticket(db,item['id'],user['id'])
    return {'versions':[{'id':item['id'],'version':1,'requestId':rid,'projectId':pid}]}

def sync_ticket(db,wid,actor):
    raw=db.execute('SELECT w.*,s.market_id FROM af2_customer_work_items w JOIN af2_customer_requests r ON r.id=w.request_id JOIN af2_customer_stores s ON s.id=r.store_id WHERE w.id=?',(wid,)).fetchone()
    if not raw:return
    d=json.loads(raw['payload']);pid=d.get('projectId') or raw['market_id']
    if not db.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone():return
    d['projectId']=pid
    if d.get('submitted') is False or d.get('stage')=='登记草稿':return
    row=db.execute('SELECT * FROM service_tickets WHERE id=?',(wid,)).fetchone();p=json.loads(row['payload']) if row else {}
    # Inventory usage and all native-only fields remain owned by their original workflow.
    p.update({'product':d.get('product',''),'description':d.get('issue',''),'date':d.get('reported',''),'deliveryDate':d.get('delivered',''),'region':d.get('region') or d.get('country',''),'category':d.get('issueType','待分类'),'problemType':d.get('problemType') or d.get('issueType','待分类'),'owner':d.get('owner',''),'dueDate':d.get('planned',''),'notes':d.get('feedback',''),'dashboardStage':d.get('stage','审核'),'executionMethod':d.get('method','待确定'),'safetyLevel':d.get('grade','待评估'),'costResponsibility':d.get('cost','待确认'),'causeAnalysis':d.get('rootCause') or d.get('cause',''),'workflowV10':d,'workflowV10Version':raw['version']})
    p['stage']='关闭与复盘' if d.get('stage')=='已关闭' else {'审核':'初步分析','工程下单':'制定方案','客户验收':'售后回访','负责人复核':'售后回访'}.get(d.get('stage'),'执行处理')
    p['dashboardStage']={'采购':'生产采购','生产':'生产采购','品质检验':'生产采购','部门处理':'现场处理','负责人复核':'客户验收'}.get(d.get('stage'),d.get('stage','审核'))
    p['dashboardSourceStage']=p['stage']
    for key in ('deviceId','model','faultDate','activationDate','lastRepairCompletedDate','rootCause','rootCauseStatus','rootCauseEvidence','correctiveAction','validationResult','validationStatus','problemPart'):
        if key in d:p[key]=d[key]
    now=core.now()
    if row:
        if row['project_id']!=pid:raise core.Problem('工单所属项目不一致',409)
        db.execute('UPDATE service_tickets SET payload=?,version=version+1,updated_at=? WHERE id=?',(json.dumps(p,ensure_ascii=False),now,wid))
    else:db.execute('INSERT INTO service_tickets(id,project_id,delivery_line_id,payload,version,created_by,created_at,updated_at) VALUES(?,?,NULL,?,1,?,?,?)',(wid,pid,json.dumps(p,ensure_ascii=False),actor,now,now))
    db.execute('INSERT INTO af2_ticket_links VALUES(?,?) ON CONFLICT(ticket_id) DO UPDATE SET core_version=excluded.core_version',(wid,(row['version']+1) if row else 1))

def handle(db,user,path,method,body=b'',headers=None,origin='http://127.0.0.1:8975'):
    headers=dict(headers or {});route=urlparse(path).path.removeprefix('/api/aftercare/')
    public=route in ('portal','submit') or (route.startswith('file/') and bool(parse_qs(urlparse(path).query).get('token')))
    if not public and not user:raise core.Problem('请先登录统一工作平台',401)
    if user and user['role']=='supplier':raise core.Problem('没有售后访问权限',403)
    if method!='GET' and not public:
        if runtime_config.read_only(user) or user['role']=='ceo':raise core.Problem('当前账号仅可查看',403)
    if user:
        if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
        seed_legacy(db)
    if route=='status':return 200,{'content-type':'application/json'},json.dumps({'user':profile(db,user)},ensure_ascii=False).encode()
    j=None
    if method!='GET' and headers.get('content-type','').startswith('application/json'):
        try:j=json.loads(body)
        except ValueError:raise core.Problem('提交格式错误')
        if not isinstance(j,dict):raise core.Problem('提交格式错误')
    if route=='work-items' and method=='POST':
        result=internal_save(db,user,j or {})
        if result:return 200,{'content-type':'application/json'},json.dumps(result).encode()
        for item in j.get('items',[]):
            row=db.execute('SELECT * FROM af2_customer_work_items WHERE id=?',(item.get('id'),)).fetchone()
            if not row:raise core.Problem('工单不存在',404)
            old=json.loads(row['payload']);req=db.execute('SELECT s.market_id FROM af2_customer_requests r JOIN af2_customer_stores s ON s.id=r.store_id WHERE r.id=?',(row['request_id'],)).fetchone()
            old['projectId']=old.get('projectId') or req['market_id'];item['projectId']=item.get('projectId') or old['projectId']
            validate_item(db,user,item,old)
    if re.fullmatch(r'requests/[^/]+/check',route) and method=='POST':
        req=db.execute('SELECT s.market_id FROM af2_customer_requests r JOIN af2_customer_stores s ON s.id=r.store_id WHERE r.id=?',(route.split('/')[1],)).fetchone()
        if not req:raise core.Problem('申请不存在',404)
        reviewer=db.execute("SELECT * FROM employees WHERE id=? AND status='active'",((j or {}).get('reviewerId'),)).fetchone()
        if not reviewer or not access.visible_project(db,dict(reviewer),req['market_id']):raise core.Problem('请选择有此项目权限的审核员',403)
    if route=='stores' and method=='POST':
        access.require(db,user,'projects',(j or {}).get('marketId'))
        if j.get('id'):
            old=db.execute('SELECT market_id FROM af2_customer_stores WHERE id=?',(j['id'],)).fetchone()
            if old and old['market_id'] and old['market_id']!=j['marketId']:raise core.Problem('已有店铺不能更换项目编号',409)
        p=core.need(db,'projects',j['marketId'])
        customer=db.execute('SELECT market_id FROM af2_customer_profiles WHERE id=?',(j.get('customerId'),)).fetchone()
        if customer and customer['market_id'] and customer['market_id']!=p['customer_id']:raise core.Problem('该项目不属于当前客户')
    if route=='profiles' and method=='POST':
        if not j.get('marketId'):raise core.Problem('请选择关联的集团客户')
        access.require(db,user,'customers',j['marketId'])
    tables=snapshot(db,None if public else user)
    if user:
        # Re-check targeted IDs against the filtered snapshot before any write.
        allowed={t['name']:{r[t['columns'].index('id')] for r in t['rows']} for t in tables if 'id' in t['columns']}
        match=re.match(r'(?:requests|work-items)/([^/]+)',route)
        if match and match[1] not in allowed.get('customer_requests' if route.startswith('requests') else 'customer_work_items',set()):raise core.Problem('记录不存在或没有项目权限',404)
        for key,table in [('customerId','customer_profiles'),('id','customer_profiles' if route=='profiles' else 'customer_stores')]:
            if j and j.get(key) and route in ('profiles','stores','invites','revoke-links') and j[key] not in allowed.get(table,set()):raise core.Problem('记录不存在或没有权限',404)
    objects={}
    if route.startswith('file/'):
        row=db.execute('SELECT object_key FROM af2_customer_files WHERE id=?',(route.split('/')[1],)).fetchone()
        # Authorization runs in the original handler before any response bytes are returned.
        if row:
            try:objects[row['object_key']]=base64.b64encode(object_storage.get('aftercare/'+row['object_key'])).decode()
            except FileNotFoundError:pass
    node=shutil.which('node') or os.environ.get('YIFUN_NODE')
    if not node:raise core.Problem('售后运行环境尚未准备好',503)
    input={'tables':tables,'user':None if public else profile(db,user),'url':origin+path.replace('/api/aftercare/','/api/customer/',1),'method':method,'headers':headers,'body':base64.b64encode(body).decode(),'objects':objects}
    result=subprocess.run([node,str(HOME/'bridge.mjs')],input=json.dumps(input,ensure_ascii=False).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    if result.returncode:raise core.Problem('售后处理服务暂时不可用，记录未保存',503)
    output=json.loads(result.stdout)
    if output['writes'] or output['objects']:
        changed=set()
        for write in output['writes']:
            sql=write['sql']
            target=re.match(r'\s*(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM)\s+([a-z_]+)',sql,re.I)
            if not target or target[1] not in TABLES:raise RuntimeError('Unexpected aftercare write')
            if target[1]=='customer_work_items':
                # Resolve all changed rows after replay; only scoped rows exist in the JS snapshot.
                if sql.lstrip().upper().startswith('INSERT'):changed.add(write['args'][0])
                elif sql.lstrip().upper().startswith('UPDATE'):changed.add(write['args'][-2])
            for name in sorted(TABLES,key=len,reverse=True):sql=re.sub(r'\b'+name+r'\b','af2_'+name,sql)
            cursor=db.execute(sql,write['args'])
            if cursor.rowcount!=write['changes']:raise core.Problem('资料已被其他同事修改，请刷新后重试',409)
        for obj in output['objects']:
            raw=base64.b64decode(obj['data'])
            if len(raw)>5*1024*1024:raise core.Problem('单个附件请控制在5MB内',413)
            object_storage.put('aftercare/'+obj['key'],raw,obj['mime'])
        for wid in changed:
            r=db.execute('SELECT id,updated_by FROM af2_customer_work_items WHERE id=?',(wid,)).fetchone()
            if r:sync_ticket(db,r['id'],r['updated_by'])
        if route in ('profiles','stores') and method=='POST':
            rid=json.loads(base64.b64decode(output['body']))['id'];db.execute('INSERT OR IGNORE INTO af2_ownership VALUES(?,?,?)',(route,rid,user['id']))
    response_body=base64.b64decode(output['body'])
    selected=parse_qs(urlparse(path).query).get('project',[''])[0]
    if route=='work-items' and method=='GET' and selected and output['status']==200:
        access.require(db,user,'projects',selected)
        response=json.loads(response_body)
        request_projects={r['id']:r['market_id'] for r in db.execute('SELECT r.id,s.market_id FROM af2_customer_requests r JOIN af2_customer_stores s ON s.id=r.store_id')}
        response['items']=[item for item in response['items'] if (item.get('projectId') or request_projects.get(item.get('cloudRequestId')))==selected]
        response_body=json.dumps(response,ensure_ascii=False).encode()
    return output['status'],output['headers'],response_body
