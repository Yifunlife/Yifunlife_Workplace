"""Canonical shared identities and department views over the SAME aftersales records."""
import json,unicodedata,time
import core,project_access as access
CENTERS={'仓库':'stock','生产部':'factory','售后部':'aftersales','售后中心':'aftersales','工程部':'engineering','工程中心':'engineering','研发 / 技术部':'engineering','技术部':'engineering','采购部':'procurement','采购中心':'procurement','工厂':'factory','生产中心':'factory','品质部':'factory','物流部':'stock','仓库与物流中心':'stock','仓库中心':'stock','安装服务部':'engineering','安装中心':'engineering','销售部':'crm','销售中心':'crm'}
LABELS={'aftersales':'售后中心','engineering':'工程中心','procurement':'采购中心','factory':'生产中心','stock':'仓库中心','crm':'销售中心'}
PEOPLE=('owner','trackingOwner','sales','designer','engineer','installer','reviewer','nextOwner','buyer','person','servicePerson')
def norm(v):return ''.join(unicodedata.normalize('NFKC',str(v or '')).split()).casefold()
def normalize(db,d,old=None):
    d=json.loads(json.dumps(d));pid=d.get('projectId');p=db.execute('SELECT p.*,c.name customer_name FROM projects p JOIN customers c ON c.id=p.customer_id WHERE p.id=?',(pid,)).fetchone()
    if not p:return d
    d.update(project=p['name'],customer=p['customer_name'],customerId=p['customer_id'])
    employees=[dict(e) for e in db.execute("SELECT id,name,role,status FROM employees WHERE role!='supplier'")]
    # Project-visible accounts only. Free text never grants project membership.
    eligible={e['id']:e for e in employees if access.visible_project(db,e,pid)}
    issues=[]
    def people(obj,prior,path=''):
        refs={}
        for k in PEOPLE:
            if k not in obj:continue
            text=str(obj.get(k) or '').strip();ident=obj.get(k+'Id');previous=(prior or {}).get('_sharedPeople',{}).get(k,{})
            if ident and ident in eligible and text in (eligible[ident]['name'],previous.get('name')):
                e=eligible[ident]
            else:
                matches=[e for e in eligible.values() if e['status']=='active' and norm(e['name'])==norm(text)] if text else []
                e=matches[0] if len(matches)==1 else None
            if e:
                obj[k]=e['name'];obj[k+'Id']=e['id'];refs[k]={'id':e['id'],'name':e['name']}
            else:
                obj.pop(k+'Id',None)
                if text:issues.append({'field':path+k,'name':text,'reason':'姓名重复或未关联有项目权限的集团账号'})
        if refs:obj['_sharedPeople']=refs
        else:obj.pop('_sharedPeople',None)
        for k in ('review','reviewDraft','engineering','production','purchase','shipment'):
            if isinstance(obj.get(k),dict):people(obj[k],(prior or {}).get(k),path+k+'.')
    people(d,old or d)
    department=d.get('department') or (d.get('review',{}).get('department') if isinstance(d.get('review'),dict) else None)
    if department in CENTERS:d['departmentCenterId']=CENTERS[department]
    if d.get('baselineId'):
        order=db.execute('SELECT * FROM order_baselines WHERE id=?',(d['baselineId'],)).fetchone()
        if not order or order['project_id']!=pid:raise core.Problem('原订单不属于当前项目',403)
        d['order']=order['number']
    elif d.get('order'):
        orders=list(db.execute('SELECT id,number FROM order_baselines WHERE project_id=? AND number=?',(pid,d['order'])))
        if len(orders)==1:d['baselineId']=orders[0]['id']
    serial=d.get('deviceId') or ''
    asset=db.execute('SELECT * FROM equipment_assets WHERE id=?',(d.get('assetId') or '',)).fetchone() if d.get('assetId') else None
    if asset and serial not in (asset['serial'],(old or d).get('sharedAssetSerial')):
        asset=None;d.pop('assetId',None)
    if not asset and serial:asset=db.execute('SELECT * FROM equipment_assets WHERE serial=? OR id=?',(serial,serial)).fetchone()
    if asset:
        if asset['project_id']!=pid:raise core.Problem('设备不属于当前项目',403)
        d.update(assetId=asset['id'],deviceId=asset['serial'],sharedAssetSerial=asset['serial'])
    d['sharedIdentityIssues']=issues
    return d

def refresh(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='af2_customer_work_items'").fetchone():return
    import aftercare
    aftercare.seed_legacy(db)
    for row in db.execute('SELECT w.*,s.market_id FROM af2_customer_work_items w JOIN af2_customer_requests q ON q.id=w.request_id JOIN af2_customer_stores s ON s.id=q.store_id').fetchall():
        old=json.loads(row['payload']);old['projectId']=old.get('projectId') or row['market_id'];new=normalize(db,old)
        if new==json.loads(row['payload']):continue
        db.execute('UPDATE af2_customer_work_items SET payload=?,version=version+1,updated_at=? WHERE id=?',(json.dumps(new,ensure_ascii=False),int(time.time()*1000),row['id']))
        aftercare.sync_ticket(db,row['id'],row['updated_by'])
    for row in db.execute('SELECT * FROM af2_department_records').fetchall():
        old=json.loads(row['payload']);old['projectId']=row['project_id'];new=normalize(db,old)
        if new!=json.loads(row['payload']):db.execute('UPDATE af2_department_records SET payload=?,version=version+1,updated_at=? WHERE kind=? AND id=?',(json.dumps(new,ensure_ascii=False),core.now(),row['kind'],row['id']))
    # Group customer/store names follow master IDs; independent contact details stay intact.
    db.execute('UPDATE af2_customer_profiles SET company=(SELECT name FROM customers WHERE id=market_id) WHERE market_id IN (SELECT id FROM customers) AND company<>(SELECT name FROM customers WHERE id=market_id)')
    db.execute('UPDATE af2_customer_stores SET name=(SELECT name FROM projects WHERE id=market_id) WHERE market_id IN (SELECT id FROM projects) AND name<>(SELECT name FROM projects WHERE id=market_id)')

def masters(db,user):
    result={'orders':[],'equipment':[]}
    for r in db.execute('SELECT b.id baselineId,b.number "order",b.project_id projectId,p.name project,c.name customer,c.contact,c.phone,p.location address FROM order_baselines b JOIN projects p ON p.id=b.project_id JOIN customers c ON c.id=p.customer_id'):
        if access.visible_project(db,user,r['projectId']):result['orders'].append(dict(r))
    for r in db.execute('SELECT e.id assetId,e.serial deviceId,e.name product,e.project_id projectId,p.name project,c.name customer FROM equipment_assets e JOIN projects p ON p.id=e.project_id JOIN customers c ON c.id=p.customer_id'):
        if access.visible_project(db,user,r['projectId']):result['equipment'].append(dict(r))
    return result

def task_centers(d):
    stage=d.get('stage')
    if stage in ('登记草稿','已关闭'):return []
    if stage=='工程下单':return ['engineering']
    if stage=='采购':return ['procurement']
    if stage in ('生产','品质检验'):return ['factory']
    if stage=='生产采购':
        destination=(d.get('engineering') or {}).get('destination') or d.get('department')
        return ['procurement'] if destination=='采购部' else ['factory'] if destination in ('工厂','品质部') else ['engineering']
    if stage=='发货物流':return ['stock']
    if stage=='现场处理':return ['engineering']
    if stage=='部门处理':return [d.get('departmentCenterId') or 'aftersales']
    return ['aftersales']

def tasks(db,user,center=None,project=None):
    rows=[]
    import aftercare
    role=aftercare.role(db,user)
    permissions={'审核':('审核人员',),'部门处理':('审核人员','工程人员'),'工程下单':('工程人员',),'采购':('采购人员',),'生产采购':('采购人员','生产人员'),'生产':('生产人员',),'品质检验':('生产人员',),'发货物流':('仓库人员',),'现场处理':('安装人员','售后专员'),'客户验收':('售后专员',),'负责人复核':('审核人员',)}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='af2_customer_work_items'").fetchone():return rows
    for row in db.execute('SELECT * FROM af2_customer_work_items ORDER BY updated_at DESC'):
        d=json.loads(row['payload']);pid=d.get('projectId')
        if d.get('submitted') is False or not access.visible_project(db,user,pid) or (project and project!=pid):continue
        scope=task_centers(d)
        if not scope or (center and center not in scope):continue
        p=db.execute('SELECT name FROM projects WHERE id=?',(pid,)).fetchone()
        rows.append({'id':row['id'],'project_id':pid,'project':p['name'] if p else d.get('project'),'work_no':d.get('workNo') or row['id'],'product':d.get('product',''),'issue':d.get('issue',''),'stage':d.get('stage'),'centers':scope,'owner_id':d.get('ownerId'),'owner':d.get('owner') if d.get('ownerId') else '待核对集团账号','due':d.get('planned') or d.get('orderPlanned'),'version':row['version'],'can_handle':role=='管理员' or role in permissions.get(d.get('stage'),()),'identity_issues':d.get('sharedIdentityIssues',[])})
    return rows
