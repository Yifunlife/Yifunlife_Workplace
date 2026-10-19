"""Durability adapter for the supplied after-sales internal installation/finance UI.
These records are private to after-sales; they never update another center's ledger.
"""
import json,math,re,time
from datetime import date,datetime
from zoneinfo import ZoneInfo
import core,project_access as access,runtime_config


def context(db,user):
    import aftercare
    items=[]
    for r in db.execute('SELECT w.*,s.market_id FROM af2_customer_work_items w JOIN af2_customer_requests q ON q.id=w.request_id JOIN af2_customer_stores s ON s.id=q.store_id'):
        d=json.loads(r['payload']);pid=d.get('projectId') or r['market_id']
        if not access.visible_project(db,user,pid):continue
        d.update(projectId=pid,cloudVersion=r['version'],cloudRequestId=r['request_id']);items.append(d)
    records=[]
    for r in db.execute('SELECT * FROM af2_department_records ORDER BY updated_at,id'):
        if not access.visible_project(db,user,r['project_id']):continue
        records.append({'kind':r['kind'],'id':r['id'],'ticketId':r['ticket_id'],'projectId':r['project_id'],'value':json.loads(r['payload']),'version':r['version']})
    return {'items':items,'records':records}


def day(value,required=False):
    if not value and not required:return ''
    try:
        result=date.fromisoformat(value).isoformat()
    except (ValueError,TypeError):raise core.Problem('请填写有效日期')
    return result


def integer(value,label):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=10000000000:raise core.Problem(label+'格式不正确')
    return value


def validate_files(db,request_id,value):
    if isinstance(value,list):
        for item in value:validate_files(db,request_id,item)
    elif isinstance(value,dict):
        if 'url' in value:
            url=value['url']
            if not isinstance(url,str) or not re.fullmatch(r'/api/aftercare/file/[a-f0-9-]+',url):raise core.Problem('附件尚未上传至云端，请重试')
            f=db.execute('SELECT request_id FROM af2_customer_files WHERE id=?',(url.rsplit('/',1)[-1],)).fetchone()
            if not f or f['request_id']!=request_id:raise core.Problem('附件不属于当前售后记录',403)
        for v in value.values():validate_files(db,request_id,v)


def save(db,user,b):
    import aftercare
    if runtime_config.read_only(user) or user['role']=='ceo':raise core.Problem('当前账号仅可查看',403)
    kind=b.get('kind');tid=b.get('ticketId');rid=b.get('id');value=b.get('value')
    if kind not in ('installation','finance') or not isinstance(value,dict) or not isinstance(rid,str) or not 1<=len(rid)<=180:raise core.Problem('提交记录格式不正确')
    if len(json.dumps(value,ensure_ascii=False))>160000:raise core.Problem('资料过长，请减少照片或签名笔画')
    ticket=access.require(db,user,'service_tickets',tid)
    work=db.execute('SELECT * FROM af2_customer_work_items WHERE id=?',(tid,)).fetchone()
    if not work:raise core.Problem('关联售后工单不存在',404)
    d=json.loads(work['payload']);role=aftercare.role(db,user)
    old=db.execute('SELECT * FROM af2_department_records WHERE kind=? AND id=?',(kind,rid)).fetchone()
    version=old['version'] if old else 0
    if b.get('version')!=version:raise core.Problem('此页资料已被其他同事更新，请刷新后重试',409)
    previous=json.loads(old['payload']) if old else None
    if old and (old['ticket_id']!=tid or old['project_id']!=ticket['project_id']):raise core.Problem('不能更改记录归属',403)
    value={**value,'ticketId':tid,'projectId':ticket['project_id']}
    if kind=='installation':
        if role not in ('管理员','安装人员','售后专员'):raise core.Problem('当前岗位不能修改售后安装资料',403)
        if rid!=tid:raise core.Problem('安装任务编号不正确')
        # A completed original service cannot be reopened from an installation page.
        if d.get('stage')=='已关闭' and (not previous or value!=previous):raise core.Problem('已关闭售后单不能修改安装记录',409)
        if value.get('status') not in ('待排期','已派工','安装中','待回传','待收货登记','售后结束'):raise core.Problem('安装状态不正确')
        for key in ('start','end','actual','received'):day(value.get(key))
        if value.get('start') and value.get('end') and value['end']<value['start']:raise core.Problem('结束日期不能早于开始日期')
        if value.get('start') and value.get('actual') and value['actual']<value['start']:raise core.Problem('实际完成不能早于开始日期')
        if value.get('status')=='已派工':
            if any(not str(value.get(k) or '').strip() for k in ('servicePerson','servicePhone','contact','customerPhone','address','owner','team','start','end','scope')):raise core.Problem('请补齐售后专员、客户、人员、施工日期和范围')
            if value.get('mode') not in ('all','evening','custom'):raise core.Problem('请选择施工时段')
        signatures=value.get('signature') or {'strokes':[]}
        strokes=signatures.get('strokes') if isinstance(signatures,dict) else None
        if not isinstance(strokes,list) or len(strokes)>100 or sum(len(s) for s in strokes if isinstance(s,list))>6000:raise core.Problem('签名资料过长或格式不正确')
        for stroke in strokes:
            if not isinstance(stroke,list):raise core.Problem('签名格式不正确')
            for p in stroke:
                if not isinstance(p,list) or len(p)!=2 or any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not 0<=x<=1 for x in p):raise core.Problem('签名格式不正确')
        validate_files(db,work['request_id'],value.get('photos',{}))
        if value.get('status')=='售后结束':
            if value.get('install'):
                if not value.get('actual') or not value.get('notes') or not value.get('finished'):raise core.Problem('请补齐实际完成日期、总体说明和完成确认')
                items=value.get('items') or []
                if not items or any(i.get('state')!='已完成' or not str(i.get('note') or '').strip() or not (value.get('photos') or {}).get(i.get('id')) for i in items):raise core.Problem('每个服务项目都需要完成结果、说明和现场照片')
                if value.get('presence')=='present' and (not value.get('signer') or not strokes):raise core.Problem('客户在场时需要客户姓名与本人签名')
                if value.get('presence')=='absent' and not value.get('absentReason'):raise core.Problem('请登记客户不在场的原因')
                if value.get('presence') not in ('present','absent'):raise core.Problem('请登记客户是否在场')
            elif not all(value.get(k) for k in ('receiver','received','method','receiptNotes')):raise core.Problem('请补齐客户收货登记')
        # Scope task lists by real projects when checking simultaneous personnel assignments.
        if value.get('status') in ('已派工','安装中') and value.get('owner') and value.get('start'):
            for row in db.execute("SELECT * FROM af2_department_records WHERE kind='installation' AND id<>?",(rid,)):
                other=json.loads(row['payload'])
                if other.get('owner')==value['owner'] and other.get('status') not in ('售后结束','待排期') and other.get('start') and value['start']<=other.get('end','') and other['start']<=value.get('end',''):
                    if value.get('mode')=='all' or other.get('mode')=='all':raise core.Problem('该人员在所选日期已有其它安排，请核对施工时段',409)
    else:
        allowed={'管理员':{'采购','生产','物流','人工','吃','住','行'},'采购人员':{'采购'},'生产人员':{'生产'},'工程人员':{'生产'},'仓库人员':{'物流'},'安装人员':{'人工','吃','住','行'},'财务人员':{'采购','生产','物流','人工','吃','住','行'},'售后专员':{'物流','人工','吃','住','行'}}
        cat=value.get('cat')
        if cat not in allowed.get(role,set()):raise core.Problem('当前岗位不能登记此类售后费用',403)
        integer(value.get('amount'),'费用金额');integer(value.get('paid',0),'已付金额')
        if value.get('paid',0)>value['amount']:raise core.Problem('已付金额不能大于费用金额')
        if value.get('payer') not in ('公司','客户'):raise core.Problem('请选择费用承担方')
        day(value.get('date'),True)
        if value.get('date')>datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat():raise core.Problem('费用日期不能晚于今天')
        if value.get('review') not in ('待核对','已核对'):raise core.Problem('费用核对状态不正确')
        if not all(str(value.get(k) or '').strip() for k in ('name','person','source')):raise core.Problem('请填写费用名称、填报人和唯一来源')
        if previous and previous.get('paid',0)>value.get('paid',0):raise core.Problem('已登记付款不能从此处减少，请联系负责人核对')
        if role not in ('管理员','财务人员') and (value.get('paid',0)!=(previous or {}).get('paid',0) or value.get('review')!=(previous or {}).get('review','待核对')):raise core.Problem('只有售后财务岗位可以核对费用及登记付款',403)
        if value.get('review')=='已核对' and not value.get('voucherUrl'):raise core.Problem('请先补充云端凭证，再进行财务核对')
        if value.get('voucherUrl'):validate_files(db,work['request_id'],{'url':value['voucherUrl']})
        if value.get('paid',0)>(previous or {}).get('paid',0):
            payments=value.get('paymentHistory') or []
            previous_payments=(previous or {}).get('paymentHistory') or []
            if not isinstance(payments,list) or payments[:len(previous_payments)]!=previous_payments:raise core.Problem('已登记付款记录不能改写')
            added=payments[len(previous_payments):]
            if not added:raise core.Problem('请填写付款凭证号和日期')
            for payment in added:
                if not isinstance(payment,dict) or not str(payment.get('reference') or '').strip():raise core.Problem('请填写付款凭证号和日期')
                day(payment.get('date'),True);integer(payment.get('amount'),'付款金额')
            if sum(p['amount'] for p in added)!=value['paid']-(previous or {}).get('paid',0):raise core.Problem('付款明细与已付金额不一致')
            if value.get('review')!='已核对':raise core.Problem('费用核对后才能登记付款')
        for row in db.execute("SELECT id,payload FROM af2_department_records WHERE kind='finance' AND id<>?",(rid,)):
            if json.loads(row['payload']).get('source')==value['source']:raise core.Problem('该来源单号与行号已登记，请勿重复计费',409)
    encoded=json.dumps(value,ensure_ascii=False)
    db.execute('INSERT INTO af2_department_records VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload,version=af2_department_records.version+1,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(kind,rid,ticket['project_id'],tid,encoded,user['id'],core.now()))
    if kind=='installation' and value.get('status')=='售后结束' and (previous or {}).get('status')!='售后结束':
        if d.get('stage') not in ('现场处理','客户验收'):raise core.Problem('当前售后工单不在现场处理或客户验收环节',409)
        d.update(stage='客户验收',actual=value.get('actual') or value.get('received'),installer=value.get('owner') or d.get('installer',''),next='客户验收后交负责人复核')
        db.execute('UPDATE af2_customer_work_items SET payload=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',(json.dumps(d,ensure_ascii=False),int(time.time()*1000),user['id'],tid));aftercare.sync_ticket(db,tid,user['id'])
    db.execute('INSERT INTO af2_account_audit VALUES(?,?,?,?,?)',(core.uid(),user['id'],rid,'保存售后内部'+kind,int(time.time()*1000)))
    return {'ok':True,'id':rid,'version':version+1,'value':value}
