"""Transactional business rules for quotation, purchasing, stock, delivery and service."""
import json
import math
import re
import sqlite3
import uuid
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
import database
import project_access as access

class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def row(db, sql, args=()):
    r=db.execute(sql,args).fetchone()
    return dict(r) if r else None

def need(db, table, key):
    result=row(db, f'SELECT * FROM {table} WHERE id=?',(key,))
    if not result: raise Problem('记录不存在，请刷新后重试',404)
    return result

def text(value, label, required=True, limit=4000):
    if not isinstance(value,str) or len(value)>limit or (required and not value.strip()): raise Problem(f'请填写有效的{label}')
    return value.strip()

def quantity(value, zero=False):
    if isinstance(value,bool): raise Problem('数量格式不正确')
    try: n=float(value)
    except (TypeError,ValueError): raise Problem('请填写有效数量')
    if not math.isfinite(n) or n<0 or (not zero and n==0) or n>1e9: raise Problem('请填写有效数量')
    return n

def money(value, zero=False):
    if isinstance(value,bool): raise Problem('金额格式不正确')
    try:
        n=Decimal(str(value)); cents=n*100
        if not n.is_finite() or cents!=cents.to_integral_value() or n<0 or (not zero and n==0) or cents>9007199254740991: raise ValueError()
        return int(cents)
    except (InvalidOperation,ValueError,TypeError): raise Problem('金额应为非负数，最多两位小数')

def day(value):
    try: return date.fromisoformat(value).isoformat()
    except (TypeError,ValueError): raise Problem('请填写有效日期')

def permit(user,*roles):
    if user['role'] not in roles: raise Problem('当前岗位不能执行此操作',403)

def audit(db,user,entity,key,action,detail):
    db.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)',(uid(),entity,key,action,user['id'],user['name'],json.dumps(detail,ensure_ascii=False),now()))

def setting(db,key): return db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()[0]

def finance_access(db,user):
    if setting(db,'finance_enabled')!='1': raise Problem('财务功能暂未开放',403)
    permit(user,'finance','ceo')

def released(db,baseline):
    approved=row(db,"SELECT id FROM release_requests WHERE baseline_id=? AND status='approved'",(baseline['id'],))
    if approved:return 'ceo'
    required=baseline['deposit_required_minor']
    if required is None:return None
    total=db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM deposit_confirmations WHERE baseline_id=? AND currency=?',(baseline['id'],baseline['currency'])).fetchone()[0]
    if required>0 and total>=required:return 'deposit'
    return None

def baseline_effective(db,line):
    change=row(db,"SELECT * FROM order_changes WHERE baseline_line_id=? AND status='applied' ORDER BY confirmed_at DESC,rowid DESC LIMIT 1",(line['id'],))
    return {**line,'effective_quantity':change['new_quantity'] if change else line['quantity'],'effective_product_id':change['new_product_id'] if change else line['product_id'],'effective_model':change['new_model'] if change else line['model']}

def inventory(db):
    return [dict(r) for r in db.execute("""SELECT p.*,COALESCE(m.balance,0) AS on_hand,COALESCE(r.reserved,0) AS reserved,
       COALESCE(m.unavailable,0) AS unavailable,COALESCE(m.balance,0)-COALESCE(m.unavailable,0)-COALESCE(r.reserved,0) AS available
       FROM products p LEFT JOIN (SELECT m.product_id,SUM(m.quantity) balance,SUM(CASE WHEN l.usable=0 THEN m.quantity ELSE 0 END) unavailable FROM stock_movements m JOIN warehouse_locations l ON l.id=m.location_id GROUP BY m.product_id) m ON m.product_id=p.id
       LEFT JOIN (SELECT product_id,SUM(quantity) reserved FROM stock_reservations WHERE status='active' GROUP BY product_id) r ON r.product_id=p.id ORDER BY p.sku,p.name""")]

def inventory_one(db,product_id):
    need(db,'products',product_id)
    on_hand=db.execute('SELECT COALESCE(SUM(m.quantity),0) FROM stock_movements m JOIN warehouse_locations l ON l.id=m.location_id WHERE m.product_id=? AND l.usable=1',(product_id,)).fetchone()[0]
    reserved=db.execute("SELECT COALESCE(SUM(quantity),0) FROM stock_reservations WHERE product_id=? AND status='active'",(product_id,)).fetchone()[0]
    return on_hand,reserved

def _view_unscoped(db,user,part,project=None):
    if user['role']=='supplier':raise Problem('供应商请进入采购中心查看自己的订单',403)
    if part=='overview':
        baselines=[dict(r) for r in db.execute('SELECT b.*,p.name project_name FROM order_baselines b JOIN projects p ON p.id=b.project_id ORDER BY b.created_at DESC')]
        if project:baselines=[b for b in baselines if b['project_id']==project]
        for b in baselines:
            b.pop('raw_snapshot',None);b['release_route']=released(db,b)
            if user['role'] in ('engineering','warehouse','installation','aftersales'):b.pop('agreed_minor',None);b.pop('deposit_required_minor',None)
            b['lines']=[]
            for l in db.execute('SELECT * FROM baseline_lines WHERE baseline_id=? ORDER BY line_order',(b['id'],)):
                line=baseline_effective(db,dict(l));line.pop('raw_snapshot',None)
                line['allocated']=db.execute('SELECT COALESCE(SUM(a.quantity),0) FROM procurement_allocations a JOIN order_items i ON i.id=a.order_item_id JOIN purchase_orders p ON p.id=i.order_id WHERE a.baseline_line_id=? AND p.archived_at IS NULL',(line['id'],)).fetchone()[0]
                line['delivered']=db.execute('SELECT COALESCE(SUM(quantity),0) FROM delivery_lines WHERE baseline_line_id=?',(line['id'],)).fetchone()[0]
                b['lines'].append(line)
        quotation_sql='SELECT id,contract_no,project_name,project_id,document_type,parent_order_id,is_finalized,final_amount,final_currency,ordered_at,voided_at,archived_at FROM quotation_history'
        clauses=[];args=[]
        if project:clauses.append('project_id=?');args.append(project)
        if user['role']=='sales':clauses.append('created_by=?');args.append(user['email'])
        quotations=[dict(r) for r in db.execute(quotation_sql+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY generated_at DESC',args)] if user['role'] in ('sales','admin','ceo') else []
        return {'projects':[dict(r) for r in db.execute('SELECT p.*,c.name customer_name FROM projects p JOIN customers c ON c.id=p.customer_id ORDER BY p.code')],
                'customers':[dict(r) for r in db.execute('SELECT * FROM customers ORDER BY code')], 'products':inventory(db),
                'suppliers':[dict(r) for r in db.execute("SELECT id,code,name FROM suppliers WHERE archived_at IS NULL ORDER BY code")],
                'baselines':baselines,'quotations':quotations,'finance_enabled':setting(db,'finance_enabled')=='1',
                'deposit_confirmation_role':setting(db,'deposit_confirmation_role'),
                'releases':[dict(r) for r in db.execute('SELECT r.*,b.number,p.name project_name FROM release_requests r JOIN order_baselines b ON b.id=r.baseline_id JOIN projects p ON p.id=b.project_id ORDER BY r.created_at DESC') if not project or r['baseline_id'] in {b['id'] for b in baselines}],
                'changes':[dict(r) for r in db.execute('SELECT c.*,l.name original_name,l.quantity original_quantity FROM order_changes c JOIN baseline_lines l ON l.id=c.baseline_line_id ORDER BY c.created_at DESC') if not project or r['project_id']==project],
                'deliveries':[dict(r) for r in db.execute('SELECT * FROM deliveries ORDER BY created_at DESC') if not project or r['project_id']==project],
                'service_requests':[dict(r) for r in db.execute('SELECT r.*,s.project_id FROM service_requests r JOIN service_tickets s ON s.id=r.ticket_id ORDER BY r.created_at DESC') if not project or r['project_id']==project],
                'reservations':[dict(r) for r in db.execute("SELECT r.*,p.name product_name FROM stock_reservations r JOIN products p ON p.id=r.product_id WHERE r.status='active' ORDER BY r.created_at")],
                'stock_history':[dict(r) for r in db.execute('SELECT m.*,p.name product_name FROM stock_movements m JOIN products p ON p.id=m.product_id ORDER BY m.created_at DESC')]}
    if part=='technical':
        permit(user,'engineering','purchasing','admin','ceo')
        items=[dict(r) for r in db.execute('SELECT i.id,i.product_name,i.model,i.specification,i.material_process,i.installation_method,i.acceptance_status,p.po_number,c.project_id FROM order_items i JOIN purchase_orders p ON p.id=i.order_id LEFT JOIN procurement_context c ON c.order_id=p.id WHERE p.archived_at IS NULL') if not project or r['project_id']==project]
        notes=[dict(r) for r in db.execute("SELECT * FROM audit_events WHERE action='工程验收意见' ORDER BY created_at DESC")]
        return {'items':items,'notes':notes}
    if part=='finance':
        finance_access(db,user)
        result=[]
        for b in db.execute('SELECT * FROM order_baselines ORDER BY created_at DESC'):
            if project and b['project_id']!=project:continue
            entries=[dict(r) for r in db.execute('SELECT * FROM customer_financial_entries WHERE baseline_id=? ORDER BY created_at',(b['id'],))]
            sums={kind:sum(e['amount_minor'] for e in entries if e['kind']==kind) for kind in ('receipt','credit','surcharge')}
            result.append({'id':b['id'],'number':b['number'],'currency':b['currency'],'agreed_minor':b['agreed_minor'],**sums,'remaining_minor':b['agreed_minor']+sums['surcharge']-sums['credit']-sums['receipt'],'entries':entries})
        return {'items':result}
    if part=='audit':
        permit(user,'admin','ceo')
        return {'items':[dict(r) for r in db.execute('SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 300')]}
    if part=='migration':
        permit(user,'admin')
        return {'items':[dict(r) for r in db.execute('SELECT id,source_system,source_environment,entity_type,legacy_id,status,target_id,imported_at FROM legacy_records ORDER BY imported_at DESC')]}
    raise Problem('页面不存在',404)

def mutate(user,action,payload):
    with database.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        return execute(db,user,action,payload)

def master_code(db,table,prefix):
    prefix=prefix+'-'+date.today().strftime('%Y%m%d')+'-'
    number=db.execute('SELECT COUNT(*) FROM '+table+' WHERE code LIKE ?',(prefix+'%',)).fetchone()[0]+1
    while db.execute('SELECT 1 FROM '+table+' WHERE code=?',(prefix+str(number).zfill(4),)).fetchone():number+=1
    return prefix+str(number).zfill(4)

def execute(db,user,action,p):
    if action=='projects' and 'new_customer' in p:
        permit(user,'admin','sales')
        if p.get('customer_id'):raise Problem('请选择已有客户或填写新客户，不能同时提交')
        customer=p['new_customer']
        if not isinstance(customer,dict):raise Problem('请填写新客户资料')
        customer_id=execute(db,user,'customers',{**customer,'code':master_code(db,'customers','C')})['id']
        p={**p,'customer_id':customer_id}
    access.guard_action(db,user,action,p)
    if action=='project-members':return access.assign(db,user,p)
    if action=='customers':
        permit(user,'admin','sales');key=uid()
        db.execute('INSERT INTO customers(id,code,name,contact,phone,email,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(key,text(p.get('code') or master_code(db,'customers','C'),'客户编号'),text(p.get('name'),'客户名称'),str(p.get('contact','')),str(p.get('phone','')),str(p.get('email','')),str(p.get('notes','')),now()))
        db.execute('UPDATE customers SET created_by=? WHERE id=?',(user['id'],key))
        audit(db,user,'customer',key,'建立客户',{'name':p['name']});return {'id':key}
    if action=='projects':
        permit(user,'admin','sales');need(db,'customers',p.get('customer_id'));key=uid()
        code=text(p.get('code') or '','项目编号',False) or master_code(db,'projects','P')
        if row(db,'SELECT id FROM projects WHERE code=?',(code,)):raise Problem('项目编号已存在，请更换编号，或留空由系统生成')
        owner=p.get('owner_id') or None
        if owner:
            permit(user,'admin');employee=need(db,'employees',owner)
            if employee['role']=='supplier' or employee['status']!='active':raise Problem('请选择使用中的内部员工担任负责人')
        db.execute('INSERT INTO projects(id,code,name,customer_id,location,owner,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(key,code,text(p.get('name'),'项目名称'),p['customer_id'],str(p.get('location','')),str(p.get('owner','')),str(p.get('notes','')),now()))
        if user['role']=='sales':owner=user['id']
        if owner:db.execute('INSERT INTO project_members VALUES(?,?,?,?,?)',(key,owner,'owner',user['id'],now()))
        audit(db,user,'project',key,'建立项目',{'name':p['name']});return {'id':key}
    if action=='master-update':
        permit(user,'admin','sales');entity=p.get('entity')
        if entity not in ('customers','projects'):raise Problem('资料类型无效')
        old=need(db,entity,p.get('id'))
        field='customer_id' if entity=='customers' else 'project_id'
        if db.execute('SELECT 1 FROM connected_sales WHERE '+field+'=?',(old['id'],)).fetchone():raise Problem('这份资料由亦玩销售工作台维护，请在原工作台修改后同步。')
        if old['version']!=p.get('version'):raise Problem('资料已更新，请刷新后重试',409)
        name=text(p.get('name'),'名称');db.execute(f'UPDATE {entity} SET name=?,version=version+1 WHERE id=?',(name,old['id']))
        audit(db,user,entity,old['id'],'修改名称',{'before':old['name'],'after':name});return {'ok':True}
    if action=='products':
        permit(user,'admin','purchasing');sku=text(p.get('sku'),'SKU');name=text(p.get('name'),'产品名称')
        if row(db,'SELECT id FROM products WHERE lower(trim(sku))=lower(trim(?))',(sku,)):raise Problem('SKU 已存在，请先核对产品',409)
        key=uid();unit=text(p.get('unit'),'单位')
        db.execute("INSERT INTO catalog_products(id,sku,name,english_name,category,family,price_note,unit,specification,brand,material,note,image_key) VALUES(?,?,?,'','','','',?,?,'','','','')",(key,sku,name,unit,str(p.get('specification',''))))
        audit(db,user,'product',key,'建立共用产品',{'sku':sku,'name':name});return {'id':key}
    if action=='order-from-quote':
        permit(user,'sales');quote=need(db,'quotation_history',p.get('quote_id'))
        if quote['created_by'].lower()!=user['email'].lower():raise Problem('只能确认自己负责的报价下单',403)
        existing=row(db,'SELECT id FROM order_baselines WHERE quote_id=?',(quote['id'],))
        if existing:return existing
        if not quote['is_finalized'] or quote['voided_at'] or quote['archived_at'] or quote['final_amount'] is None:raise Problem('请先确认报价及最终成交金额')
        project=need(db,'projects',quote['project_id']);snapshot=json.loads(quote['snapshot_json'] or '{}')
        required=money(p['deposit_required'],zero=True) if p.get('deposit_required') not in (None,'') else None
        if required==0:raise Problem('零订金请保留待确认，并申请 CEO 特批')
        amount=money(quote['final_amount']);currency=quote['final_currency']
        if required is not None and required>amount:raise Problem('订金要求不能超过本单成交金额')
        kind=quote['document_type'];parent=quote['parent_order_id']
        if kind=='addition':
            old=need(db,'order_baselines',parent)
            if old['project_id']!=project['id']:raise Problem('增项必须属于原订单项目')
        elif kind!='original':raise Problem('报价类型无效')
        items=[];seen=set();cart=snapshot.get('cart',{})
        for i,item in enumerate(snapshot.get('products',[])):
            source=str(item.get('id',''));qty=cart.get(source,0)
            if not qty:continue
            qty=quantity(qty)
            if source in seen:raise Problem('报价快照包含重复产品行，请先核对')
            seen.add(source);candidate=item.get('catalogProductId') or source
            product=row(db,'SELECT * FROM products WHERE id=?',(candidate,))
            if not product:raise Problem('报价中有未关联共用产品，请先在报价导入中确认 SKU 对应关系')
            items.append((uid(),product['id'],source,text(item.get('name'),'产品名称'),str(item.get('sku','')),str(item.get('model','')),str(item.get('spec','')),str(item.get('unit','')),qty,i,json.dumps(item,ensure_ascii=False)))
        if not items:raise Problem('报价明细为空，不能下单')
        if any(quantity(qty)>0 and key not in seen for key,qty in cart.items()):raise Problem('报价快照缺少部分产品明细，不能遗漏下单')
        key=uid();stamp=now();number=f"SO-{project['code']}-{db.execute('SELECT COUNT(*) FROM order_baselines WHERE project_id=?',(project['id'],)).fetchone()[0]+1:03d}"
        db.execute('INSERT INTO order_baselines VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,number,project['id'],quote['id'],kind,parent,currency,amount,quote['snapshot_json'],required,user['id'],stamp))
        for line in items:db.execute('INSERT INTO baseline_lines VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(line[0],key,*line[1:]))
        db.execute('UPDATE quotation_history SET ordered_at=? WHERE id=?',(stamp,quote['id']))
        audit(db,user,'order',key,'报价确认下单',{'quote_id':quote['id'],'number':number,'deposit_required_minor':required});return {'id':key,'number':number}
    if action=='request-release':
        permit(user,'sales','purchasing');b=need(db,'order_baselines',p.get('baseline_id'));reason=text(p.get('reason'),'特批原因')
        if released(db,b):raise Problem('该订单已满足下单放行条件')
        key=uid();db.execute('INSERT INTO release_requests(id,baseline_id,reason,requested_by,created_at) VALUES(?,?,?,?,?)',(key,b['id'],reason,user['id'],now()))
        audit(db,user,'release',key,'申请特殊放行',{'baseline_id':b['id'],'reason':reason});return {'id':key}
    if action=='decide-release':
        permit(user,'ceo');r=need(db,'release_requests',p.get('id'));decision=p.get('decision')
        if decision not in ('approved','rejected'):raise Problem('请选择批准或拒绝')
        if r['status']!='pending':raise Problem('此申请已处理，请刷新',409)
        note=text(p.get('note'),'审批说明')
        db.execute('UPDATE release_requests SET status=?,decided_by=?,decision_note=?,decided_at=? WHERE id=?',(decision,user['id'],note,now(),r['id']))
        audit(db,user,'release',r['id'],'CEO 审批',{'decision':decision,'note':note});return {'ok':True}
    if action=='confirm-deposit':
        configured=setting(db,'deposit_confirmation_role')
        if not configured:raise Problem('订金确认岗位尚未指定，请由 CEO 特批或先完成岗位配置',403)
        permit(user,configured);b=need(db,'order_baselines',p.get('baseline_id'));amount=money(p.get('amount'));reference=text(p.get('reference'),'到账凭证号')
        if p.get('currency')!=b['currency']:raise Problem('订金币种与订单不一致')
        key=uid();db.execute('INSERT INTO deposit_confirmations VALUES(?,?,?,?,?,?,?)',(key,b['id'],amount,b['currency'],reference,user['id'],now()))
        audit(db,user,'deposit',key,'确认订金到账',{'baseline_id':b['id'],'amount_minor':amount,'reference':reference});return {'id':key}
    if action=='create-po':return create_po(db,user,p)
    if action.startswith('change-'):return change(db,user,action,p)
    if action.startswith('stock-') or action=='deliver':return stock(db,user,action,p)
    if action=='finance-entry':return financial(db,user,p)
    if action.startswith('service-'):return service(db,user,action,p)
    if action.startswith('migration-'):return migration(db,user,action,p)
    if action=='technical-review':
        permit(user,'engineering','purchasing');item=need(db,'order_items',p.get('item_id'));note=text(p.get('note'),'规格／验收判断')
        audit(db,user,'purchase_item',item['id'],'工程验收意见',{'note':note});return {'ok':True}
    raise Problem('操作不存在',404)

def shadow_user(db,user):
    stamp=now()
    db.execute("INSERT INTO users(id,email,name,role,supplier_id,password_hash,password_salt,status,created_at,updated_at) VALUES(?,?,?, ?,?,'workspace','workspace','active',?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email,name=excluded.name,status='active',supplier_id=excluded.supplier_id",(user['id'],user['email'],user['name'],'supplier' if user['role']=='supplier' else 'purchaser',user.get('supplier_id'),stamp,stamp))

    if user['role']!='supplier':
        mapped={'purchasing':'purchaser','admin':'office','ceo':'boss'}.get(user['role'],user['role'])
        db.execute('INSERT INTO staff_roles VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET role=excluded.role',(user['id'],mapped))

def create_po(db,user,p):
    permit(user,'purchasing');shadow_user(db,user)
    supplier=need(db,'suppliers',p.get('supplierId'))
    if supplier['archived_at']:raise Problem('供应商已停用')
    purpose=p.get('purpose');baseline=None;project=None;service_request=None;engineering_id=None
    if purpose=='project':
        baseline=need(db,'order_baselines',p.get('baselineId'))
        if not released(db,baseline):raise Problem('订金条件尚未满足，须等待到账确认或 CEO 特批',403)
        project=need(db,'projects',baseline['project_id'])
    elif purpose=='service':
        service_request=need(db,'service_requests',p.get('serviceRequestId'))
        if service_request['status']!='pending':raise Problem('售后采购申请已处理',409)
        ticket=need(db,'service_tickets',service_request['ticket_id']);project=need(db,'projects',ticket['project_id'])
    elif purpose!='stock':raise Problem('请选择项目采购、仓库备货或售后采购')
    items=p.get('items',[])
    if baseline:
        from operations import purchase_engineering
        engineering_id=purchase_engineering(db,user,baseline,items)
    if not isinstance(items,list) or not 1<=len(items)<=500:raise Problem('请填写采购明细')
    order_date=day(p.get('orderDate'));ship_date=day(p.get('requiredShipDate'))
    if ship_date<order_date:raise Problem('要求发货日期不能早于下单日期')
    defaults=row(db,'SELECT * FROM supplier_commercial_terms WHERE supplier_id=?',(supplier['id'],))
    if p.get('supplierTermsRevision',0)!=(defaults['revision'] if defaults else 0):raise Problem('供应商条件已更新，请重新核对',409)
    terms=p.get('commercialTerms',json.loads(defaults['terms_json']) if defaults else {})
    if not isinstance(terms,dict):raise Problem('商务条件格式无效')
    fields=('production','transport','credit','payment','invoice','minimum_order')
    terms={**{k:str(terms.get(k,''))[:2000] for k in fields},'price_basis':terms.get('price_basis','unknown'),'tax_rate_bps':terms.get('tax_rate_bps'),'currency':'CNY','notes':str(terms.get('notes',''))[:2000],'order_materials':str(terms.get('order_materials',''))[:2000]}
    confirmed=p.get('commercialConfirmed') is True
    rate=terms['tax_rate_bps'];basis=terms['price_basis']
    if basis not in ('unknown','inclusive','exclusive') or (rate is not None and (isinstance(rate,bool) or not isinstance(rate,int) or not 0<=rate<=10000)):raise Problem('价格口径或税率无效')
    if confirmed and (basis=='unknown' or rate is None or any(not terms[k].strip() for k in fields)):raise Problem('请完整核对商务条件及税率')
    stamp=now();key=uid();prefix='PO-'+(project['code'] if project else 'STOCK');seq=db.execute('SELECT COUNT(*) FROM purchase_orders WHERE po_number LIKE ?',(prefix+'-%',)).fetchone()[0]+1
    number=f'{prefix}-{seq:03d}';parsed=[];seen=set();total=0
    for item in items:
        product=need(db,'products',item.get('productId'));qty=quantity(item.get('quantity'));price=money(item.get('unitPrice'),zero=True)
        if qty!=int(qty):raise Problem('采购数量须为整数')
        line=None
        if baseline:
            line=baseline_effective(db,need(db,'baseline_lines',item.get('baselineLineId')))
            if line['baseline_id']!=baseline['id'] or line['effective_product_id']!=product['id']:raise Problem('采购明细与已确认的订单产品不一致')
            if line['id'] in seen:raise Problem('同一需求行请合并数量')
            seen.add(line['id'])
            allocated=db.execute('SELECT COALESCE(SUM(a.quantity),0) FROM procurement_allocations a JOIN order_items i ON i.id=a.order_item_id JOIN purchase_orders o ON o.id=i.order_id WHERE a.baseline_line_id=? AND o.archived_at IS NULL',(line['id'],)).fetchone()[0]
            if qty+allocated>line['effective_quantity']+1e-6:raise Problem('采购数量超过剩余需求，请核对已分配采购单')
        if service_request and (len(items)!=1 or product['id']!=service_request['product_id'] or qty!=service_request['quantity']):raise Problem('售后采购必须与申请配件及数量一致')
        product_type=text(item.get('productType'),'产品类型')
        if product_type not in ('配件类','电气类','安全防护类','成品设备类','定制加工类','原材料类','工具类'):raise Problem('产品类型无效')
        amount=int(Decimal(str(qty))*price);total+=amount
        parsed.append((uid(),product,line,qty,price,amount,item,product_type))
    status='confirmed' if confirmed else 'unverified'
    db.execute('INSERT INTO purchase_orders(id,po_number,supplier_id,project_name,order_date,required_ship_date,status,purchaser_name,internal_requirements,created_by,created_at,updated_at,commercial_terms_json,commercial_status,commercial_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',(key,number,supplier['id'],project['name'] if project else '仓库备货',order_date,ship_date,'ready_to_ship' if supplier['is_online_purchase'] else 'pending_confirmation',user['name'],str(p.get('internalRequirements','')),user['id'],stamp,stamp,json.dumps(terms,ensure_ascii=False),status))
    db.execute('INSERT INTO procurement_context VALUES(?,?,?,?,?,?)',(key,project['id'] if project else None,baseline['id'] if baseline else None,purpose,service_request['ticket_id'] if service_request else None,stamp))
    if engineering_id:db.execute('INSERT INTO engineering_purchase_links VALUES(?,?)',(key,engineering_id))
    for item_id,product,line,qty,price,amount,item,ptype in parsed:
        db.execute('INSERT INTO order_items(id,order_id,product_name,product_type,product_category,quantity,unit_price,amount,specification,created_at,unit,model,color,material_process,installation_method,packaging_volume,product_id,baseline_line_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(item_id,key,product['name'],ptype if ptype not in ('原材料类','工具类') else '配件类',ptype,qty,price/100,amount/100,str(item.get('specification',product['specification'])),stamp,product['unit'],line['effective_model'] if line else str(item.get('model','')),str(item.get('color','')),str(item.get('materialProcess','')),str(item.get('installationMethod','')),str(item.get('packagingVolume','')),product['id'],line['id'] if line else None))
        if line:db.execute('INSERT INTO procurement_allocations VALUES(?,?,?,?)',(uid(),line['id'],item_id,qty))
    net=total;tax=0;payable=total
    if confirmed:
        if basis=='inclusive':net=int((Decimal(total)*10000/(10000+rate)).quantize(Decimal('1'),rounding='ROUND_HALF_UP'));tax=total-net
        else:tax=int((Decimal(total)*rate/10000).quantize(Decimal('1'),rounding='ROUND_HALF_UP'));payable=net+tax
    db.execute('INSERT INTO order_settlements(order_id,net_cents,tax_cents,payable_cents) VALUES(?,?,?,?)',(key,net,tax,payable))
    db.execute('INSERT INTO commercial_history(id,order_id,actual_json,status,reason,actor_id,actor_name,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid(),key,json.dumps(terms,ensure_ascii=False),status,'创建时保留执行条件',user['id'],user['name'],stamp))
    db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?)',(uid(),key,'created','共用项目需求建立采购单',user['id'],user['name'],stamp))
    if service_request:db.execute("UPDATE service_requests SET status='ordered',order_id=? WHERE id=?",(key,service_request['id']))
    audit(db,user,'purchase',key,'建立采购单',{'number':number,'purpose':purpose,'baseline_id':baseline['id'] if baseline else None})
    return {'ok':True,'orderId':key,'itemIds':[r[0] for r in parsed]}

def change(db,user,action,p):
    if action=='change-create':
        permit(user,'sales');line=baseline_effective(db,need(db,'baseline_lines',p.get('baseline_line_id')));baseline=need(db,'order_baselines',line['baseline_id'])
        if row(db,"SELECT id FROM order_changes WHERE baseline_line_id=? AND status IN ('draft','confirmed')",(line['id'],)):raise Problem('此产品已有待处理变更',409)
        product=need(db,'products',p.get('new_product_id'));qty=quantity(p.get('new_quantity'),zero=True)
        if qty>line['effective_quantity']:raise Problem('增加数量请另建增项报价单')
        if qty==line['effective_quantity'] and product['id']==line['effective_product_id'] and str(p.get('new_model',''))==line['effective_model']:raise Problem('没有数量或型号变更')
        key=uid();db.execute('INSERT INTO order_changes(id,project_id,baseline_line_id,new_product_id,new_quantity,new_model,reason,customer_evidence,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,baseline['project_id'],line['id'],product['id'],qty,str(p.get('new_model','')),text(p.get('reason'),'变更原因'),text(p.get('customer_evidence'),'客户确认记录'),user['id'],now()))
        audit(db,user,'change',key,'提出变更',p);return {'id':key}
    c=need(db,'order_changes',p.get('id'))
    if c['version']!=p.get('version'):raise Problem('变更已处理，请刷新',409)
    if action=='change-confirm':
        permit(user,'sales')
        if c['status']!='draft':raise Problem('仅草稿可确认')
        db.execute("UPDATE order_changes SET status='confirmed',confirmed_by=?,confirmed_at=?,version=version+1 WHERE id=?",(user['id'],now(),c['id']))
        audit(db,user,'change',c['id'],'销售确认',{'evidence':c['customer_evidence']});return {'ok':True}
    if action=='change-apply':
        permit(user,'purchasing')
        if c['status']!='confirmed':raise Problem('须先经销售确认')
        line=baseline_effective(db,need(db,'baseline_lines',c['baseline_line_id']))
        linked=[dict(r) for r in db.execute('SELECT i.*,a.id allocation_id,a.quantity allocation_quantity FROM procurement_allocations a JOIN order_items i ON i.id=a.order_item_id JOIN purchase_orders o ON o.id=i.order_id WHERE a.baseline_line_id=? AND o.archived_at IS NULL',(line['id'],))]
        delivered=db.execute('SELECT COALESCE(SUM(quantity),0) FROM delivery_lines WHERE baseline_line_id=?',(line['id'],)).fetchone()[0]
        if delivered>c['new_quantity']:raise Problem('已交付数量超过变更后的数量，须先核对退回实物；原交付记录会保留')
        if any(i['shipped_quantity'] or i['received_quantity'] or i['stocked_quantity'] or i['production_completed'] for i in linked):raise Problem('关联采购已生产完成或发货，请先在采购异常处理中核对实物处置，再处理未执行需求')
        allocation=p.get('allocations',[])
        if not isinstance(allocation,list) or {a.get('item_id') for a in allocation}!={i['id'] for i in linked}:raise Problem('请逐项填写关联采购单调整后的数量和单价')
        allocation_map={a['item_id']:a for a in allocation}
        if sum(quantity(a.get('quantity'),zero=True) for a in allocation)>c['new_quantity']+1e-6:raise Problem('调整后采购总数超过变更后的需求')
        product=need(db,'products',c['new_product_id'])
        for item in linked:
            a=allocation_map[item['id']];qty=quantity(a.get('quantity'),zero=True)
            if not qty:raise Problem('整行取消须在采购异常处理中作废未执行采购单，再应用变更')
            if qty!=int(qty):raise Problem('采购数量须为整数')
            price=money(a.get('unit_price'),zero=True)
            db.execute('INSERT INTO purchase_item_changes(id,change_id,item_id,old_product,old_model,old_quantity,old_price,new_product,new_model,new_quantity,new_price,new_name,new_unit,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid(),c['id'],item['id'],item['product_id'],item['model'],item['quantity'],item['unit_price'],product['id'],c['new_model'],qty,price/100,product['name'],product['unit'],user['id'],now()))
            db.execute('UPDATE procurement_allocations SET quantity=? WHERE id=?',(qty,item['allocation_id']))
            db.execute("UPDATE purchase_orders SET commercial_status='unverified',commercial_revision=commercial_revision+1,updated_at=? WHERE id=?",(now(),item['order_id']))
            audit(db,user,'purchase_item',item['id'],'执行销售变更',{'change_id':c['id'],'before':item,'after':a,'product_id':product['id']})
        db.execute("UPDATE order_changes SET status='applied',version=version+1 WHERE id=?",(c['id'],))
        audit(db,user,'change',c['id'],'采购执行变更',{'financial_status':'待财务开放后核对差额'});return {'ok':True}
    raise Problem('变更操作不存在',404)

def stock(db,user,action,p):
    if action=='stock-reserve':
        permit(user,'warehouse','aftersales');product=need(db,'products',p.get('product_id'));qty=quantity(p.get('quantity'));purpose=p.get('purpose');line=None;ticket=None
        if purpose=='delivery':
            permit(user,'warehouse');line=baseline_effective(db,need(db,'baseline_lines',p.get('baseline_line_id')))
            if product['id']!=line['effective_product_id']:raise Problem('发货型号须与销售确认后的型号一致')
            used=db.execute('SELECT COALESCE(SUM(quantity),0) FROM delivery_lines WHERE baseline_line_id=?',(line['id'],)).fetchone()[0]
            reserved=db.execute("SELECT COALESCE(SUM(quantity),0) FROM stock_reservations WHERE baseline_line_id=? AND status='active'",(line['id'],)).fetchone()[0]
            if used+reserved+qty>line['effective_quantity']+1e-6:raise Problem('占用数量超过尚未交付需求')
        elif purpose=='service':ticket=need(db,'service_tickets',p.get('ticket_id'))
        else:raise Problem('请选择占用用途')
        on_hand,reserved=inventory_one(db,product['id'])
        if qty>on_hand-reserved+1e-6:raise Problem('可用库存不足，请先采购补货')
        key=uid();db.execute('INSERT INTO stock_reservations(id,product_id,quantity,purpose,baseline_line_id,ticket_id,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(key,product['id'],qty,purpose,line['id'] if line else None,ticket['id'] if ticket else None,user['id'],now()))
        audit(db,user,'reservation',key,'占用库存',p);return {'id':key}
    r=need(db,'stock_reservations',p.get('id'))
    if r['status']!='active':raise Problem('此库存占用已处理，请刷新',409)
    if action=='stock-cancel':
        permit(user,'warehouse','aftersales')
        if user['role']=='aftersales' and r['actor_id']!=user['id']:raise Problem('只能撤回自己的领用申请',403)
        db.execute("UPDATE stock_reservations SET status='cancelled' WHERE id=?",(r['id'],));audit(db,user,'reservation',r['id'],'取消占用',{});return {'ok':True}
    permit(user,'warehouse')
    if action=='deliver' and r['purpose']!='delivery':raise Problem('请选择客户交付占用')
    if action=='stock-issue' and r['purpose']!='service':raise Problem('请选择售后领用申请')
    if action not in ('deliver','stock-issue'):raise Problem('库存操作不存在',404)
    if r['purpose']=='delivery':
        line=baseline_effective(db,need(db,'baseline_lines',r['baseline_line_id']))
        if line['effective_product_id']!=r['product_id']:raise Problem('销售已变更型号，请重新占用正确产品')
        delivered=db.execute('SELECT COALESCE(SUM(quantity),0) FROM delivery_lines WHERE baseline_line_id=?',(line['id'],)).fetchone()[0]
        if delivered+r['quantity']>line['effective_quantity']+1e-6:raise Problem('发货超出已确认数量，请重新核对占用')
        baseline=need(db,'order_baselines',line['baseline_id'])
        carrier=text(p.get('carrier'),'承运方式');tracking=text(p.get('tracking_number'),'运单号／自提签收记录');delivery_date=day(p.get('delivered_at'))
    from operations import balance
    location=need(db,'warehouse_locations',p.get('location_id') or 'unassigned')
    if not location['usable'] or balance(db,r['product_id'],location['id'])<r['quantity']-1e-6:raise Problem('出库库位可用数量不足，请选择正确库位或拆分占用数量')
    movement=uid();db.execute("UPDATE stock_reservations SET status='issued' WHERE id=?",(r['id'],))
    db.execute('INSERT INTO stock_movements(id,product_id,quantity,kind,order_item_id,ticket_id,reference_id,note,actor_id,created_at,location_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(movement,r['product_id'],-r['quantity'],'delivery' if r['purpose']=='delivery' else 'service_issue',None,r['ticket_id'],r['id'],str(p.get('note','')),user['id'],now(),location['id']))
    if r['purpose']=='delivery':
        key=uid();number='DL-'+datetime.now().strftime('%Y%m%d')+'-'+key[:8]
        db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',(key,baseline['project_id'],number,carrier,tracking,delivery_date,user['id'],now()))
        product=need(db,'products',r['product_id'])
        db.execute('INSERT INTO delivery_lines VALUES(?,?,?,?,?,?,?,?)',(uid(),key,line['id'],r['product_id'],r['quantity'],product['name'],line['effective_model'],movement))
        audit(db,user,'delivery',key,'客户发货',{'reservation_id':r['id'],'movement_id':movement});return {'id':key,'number':number}
    ticket=need(db,'service_tickets',r['ticket_id']);payload=json.loads(ticket['payload']);product=need(db,'products',r['product_id'])
    payload.setdefault('partsUsed',[]).append({'partId':product['id'],'sku':product['sku'],'name':product['name'],'qty':r['quantity'],'unit':product['unit'],'date':date.today().isoformat(),'note':str(p.get('note','')),'movementId':movement})
    db.execute('UPDATE service_tickets SET payload=?,version=version+1,updated_at=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),now(),ticket['id']))
    audit(db,user,'service_ticket',ticket['id'],'仓库发出售后配件',{'movement_id':movement,'quantity':r['quantity']});return {'ok':True}

def financial(db,user,p):
    finance_access(db,user);baseline=need(db,'order_baselines',p.get('baseline_id'));kind=p.get('kind')
    if kind not in ('receipt','credit','surcharge'):raise Problem('款项类型无效')
    if p.get('currency')!=baseline['currency']:raise Problem('请使用订单币种登记，不能直接混算不同币种')
    reversal=p.get('reversal_of') or None;change_id=p.get('change_id') or None
    if reversal:
        original=need(db,'customer_financial_entries',reversal)
        if original['baseline_id']!=baseline['id'] or original['kind']!=kind or original['reversal_of']:raise Problem('请选择同一订单的原始记录冲销')
        amount=-original['amount_minor'];change_id=original['change_id']
    else:
        amount=money(p.get('amount'))
        if kind in ('credit','surcharge'):
            c=need(db,'order_changes',change_id)
            l=need(db,'baseline_lines',c['baseline_line_id'])
            if l['baseline_id']!=baseline['id'] or c['status'] not in ('confirmed','applied'):raise Problem('差额须关联销售已确认的本单变更')
    key=uid();reference=text(p.get('reference'),'凭证号');note=text(p.get('note'),'款项说明');record_date=day(p.get('record_date'))
    db.execute('INSERT INTO customer_financial_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,baseline['project_id'],baseline['id'],kind,amount,baseline['currency'],reference,note,change_id,reversal,user['id'],record_date,now()))
    audit(db,user,'finance',key,'追加财务记录',{'kind':kind,'amount_minor':amount,'reversal_of':reversal});return {'id':key}

def service(db,user,action,p):
    permit(user,'aftersales')
    if action=='service-request':
        ticket=need(db,'service_tickets',p.get('ticket_id'));product=need(db,'products',p.get('product_id'));qty=quantity(p.get('quantity'));key=uid()
        db.execute('INSERT INTO service_requests(id,ticket_id,product_id,quantity,note,created_by,created_at) VALUES(?,?,?,?,?,?,?)',(key,ticket['id'],product['id'],qty,text(p.get('note'),'采购原因'),user['id'],now()))
        audit(db,user,'service_request',key,'申请售后采购',p);return {'id':key}
    if action=='service-part':
        product=need(db,'products',p.get('product_id'));minimum=quantity(p.get('min_stock',0),zero=True)
        db.execute('INSERT INTO service_parts VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET min_stock=excluded.min_stock,notes=excluded.notes',(product['id'],minimum,str(p.get('notes',''))))
        audit(db,user,'product',product['id'],'登记售后常用配件',p);return {'ok':True}
    if action=='service-save':
        records=p.get('records',[])
        if not isinstance(records,list) or len(records)>500:raise Problem('保存数量过多，请分批处理')
        saved={}
        for record in records:
            payload=record.get('payload');key=text(record.get('id'),'售后单号');version=record.get('version',0)
            if not isinstance(payload,dict):raise Problem('售后记录格式错误')
            project=access.require(db,user,'projects',payload.get('projectId'));old=row(db,'SELECT * FROM service_tickets WHERE id=?',(key,));delivery=payload.get('deliveryLineId') or None
            if old:
                access.require(db,user,'service_tickets',key)
                if old['version']!=version:raise Problem(f'售后单 {key} 已被他人更新，请刷新后合并修改',409)
                prior=json.loads(old['payload'])
                if payload.get('partsUsed',[])!=prior.get('partsUsed',[]):raise Problem('配件领用由仓库出库生成，不能手动覆盖')
                if project['id']!=old['project_id']:raise Problem('已有售后单不能直接换项目')
            elif version!=0:raise Problem('售后记录不存在，请刷新',409)
            elif payload.get('partsUsed'):raise Problem('历史领用请先提交迁移核对，不能直接形成新库存扣减')
            if delivery:
                link=row(db,'SELECT d.project_id FROM delivery_lines l JOIN deliveries d ON d.id=l.delivery_id WHERE l.id=?',(delivery,))
                if not link or link['project_id']!=project['id']:raise Problem('售后须关联本项目实际交付的产品')
            payload['id']=key;stamp=now()
            if old:db.execute('UPDATE service_tickets SET delivery_line_id=?,payload=?,version=version+1,updated_at=? WHERE id=?',(delivery,json.dumps(payload,ensure_ascii=False),stamp,key))
            else:db.execute('INSERT INTO service_tickets VALUES(?,?,?,?,?,?,?,?)',(key,project['id'],delivery,json.dumps(payload,ensure_ascii=False),1,user['id'],stamp,stamp))
            saved[key]=version+1;audit(db,user,'service_ticket',key,'保存售后单',{'previous_version':version})
        return {'versions':saved}
    raise Problem('售后操作不存在',404)

def _service_view_unscoped(db,user):
    permit(user,'aftersales','admin','ceo','sales')
    projects=[{'id':r['id'],'name':r['name'],'contractNo':r['code'],'customer':r['customer_name'],'location':r['location'],'address':r['location'],'client':r['customer_name'],'contact':r['contact'],'phone':r['phone'],'owner':r['owner'],'status':r['status']} for r in db.execute('SELECT p.*,c.name customer_name,c.contact,c.phone FROM projects p JOIN customers c ON c.id=p.customer_id')]
    tickets=[dict(r) for r in db.execute('SELECT * FROM service_tickets ORDER BY created_at DESC')]
    parts=[{'id':r['id'],'sku':r['sku'],'name':r['name'],'stock':r['available'],'onHand':r['on_hand'],'reserved':r['reserved'],'unit':r['unit'],'minStock':0,'notes':''} for r in inventory(db)]
    part_settings={r['product_id']:dict(r) for r in db.execute('SELECT * FROM service_parts')}
    for p in parts:
        s=part_settings.get(p['id'],{});p.update(minStock=s.get('min_stock',0),notes=s.get('notes',''))
    deliveries=[dict(r) for r in db.execute('SELECT l.*,d.project_id,d.number,d.delivered_at FROM delivery_lines l JOIN deliveries d ON d.id=l.delivery_id')]
    requests=[]
    for r in db.execute('SELECT r.*,p.name,p.unit,o.po_number,o.required_ship_date,s.name supplier_name,COALESCE(SUM(i.received_quantity),0) received,COALESCE(SUM(i.stocked_quantity),0) stocked FROM service_requests r LEFT JOIN products p ON p.id=r.product_id LEFT JOIN purchase_orders o ON o.id=r.order_id LEFT JOIN suppliers s ON s.id=o.supplier_id LEFT JOIN order_items i ON i.order_id=o.id GROUP BY r.id'):
        status='待采购' if r['status']=='pending' else '已到货' if r['stocked']>=r['quantity'] else '部分到货' if r['received']>0 else '已下单'
        requests.append({'id':r['po_number'] or 'SR-'+r['id'][:8],'requestId':r['id'],'ticketId':r['ticket_id'],'partId':r['product_id'],'partName':r['name'],'qty':r['quantity'],'unit':r['unit'],'supplier':r['supplier_name'],'expectedDate':r['required_ship_date'],'notes':r['note'],'status':status,'orderDate':r['created_at'][:10]})

    return {'projects':projects,'tickets':[json.loads(r['payload']) for r in tickets],'parts':parts,'procurements':requests,'versions':{r['id']:r['version'] for r in tickets},'deliveries':deliveries,'role':user['role']}

def migration(db,user,action,p):
    permit(user,'admin')
    if action=='migration-stage':
        source=text(p.get('source_system'),'来源系统');environment=text(p.get('source_environment'),'来源环境');entity=text(p.get('entity_type'),'记录类型');records=p.get('records')
        if not isinstance(records,list) or not 1<=len(records)<=500:raise Problem('每批暂存 1 至 500 条原始记录')
        for record in records:
            legacy=text(str(record.get('id','')),'原系统记录编号')
            existing=row(db,'SELECT * FROM legacy_records WHERE source_system=? AND source_environment=? AND entity_type=? AND legacy_id=?',(source,environment,entity,legacy))
            raw=json.dumps(record,ensure_ascii=False,sort_keys=True)
            if existing:
                if existing['raw_json']!=raw:raise Problem(f'原记录 {legacy} 与已暂存版本不一致，请使用新的来源批次标识',409)
                continue
            db.execute('INSERT INTO legacy_records(id,source_system,source_environment,entity_type,legacy_id,raw_json,imported_at) VALUES(?,?,?,?,?,?,?)',(uid(),source,environment,entity,legacy,raw,now()))
        audit(db,user,'migration',source,'暂存原始数据',{'count':len(records),'environment':environment,'entity':entity});return {'ok':True,'count':len(records)}
    raise Problem('迁移操作不存在',404)


def project_records(db,user,records):
    result=[]
    for p in records:
        if not access.visible_project(db,user,p['id']):continue
        assigned=access.members(db,p['id'])
        active=[m for m in assigned if m['status']=='active']
        owner=next((m for m in active if m['assignment_role']=='owner'),None)
        p.update(legacy_owner=p['owner'],owner=owner['name'] if owner else '',owner_id=owner['employee_id'] if owner else None,
                 member_count=len(active),member_names=[m['name'] for m in active],members=assigned if user['role']=='admin' else [])
        result.append(p)
    return result


def view(db,user,part,project=None):
    if project:access.require(db,user,'projects',project)
    result=_view_unscoped(db,user,part,project)
    if part=='overview':
        import connections
        config=connections.configuration()
        result['online_quote']=bool(config.get('enabled') and config.get('quote_token'))
        result['projects']=project_records(db,user,result['projects'])
        result['customers']=[c for c in result['customers'] if access.visible_customer(db,user,c['id'])]
        entities={'baselines':'order_baselines','quotations':'quotation_history','releases':'release_requests',
                  'changes':'order_changes','deliveries':'deliveries','service_requests':'service_requests',
                  'reservations':'stock_reservations','stock_history':'stock_movements'}
        for field,entity in entities.items():
            result[field]=[r for r in result[field] if access.visible_entity(db,user,entity,r['id'])]
        if project:
            # Inventory quantities stay shared; demand and history follow the selected project.
            def in_project(entity,key):
                if entity=='stock_reservations':
                    r=need(db,entity,key)
                    if r['ticket_id']:return need(db,'service_tickets',r['ticket_id'])['project_id']==project
                    l=need(db,'baseline_lines',r['baseline_line_id'])
                    return need(db,'order_baselines',l['baseline_id'])['project_id']==project
                r=need(db,entity,key)
                if r['ticket_id']:return need(db,'service_tickets',r['ticket_id'])['project_id']==project
                if r['order_item_id']:
                    i=need(db,'order_items',r['order_item_id']);c=row(db,'SELECT project_id FROM procurement_context WHERE order_id=?',(i['order_id'],))
                    return c and c['project_id']==project
                return bool(r['reference_id'] and row(db,'SELECT id FROM stock_reservations WHERE id=?',(r['reference_id'],)) and in_project('stock_reservations',r['reference_id']))
            for field in ('reservations','stock_history'):
                result[field]=[r for r in result[field] if in_project(entities[field],r['id'])]
        result['stock_history']=result['stock_history'][:100]
    elif part=='technical':
        result['items']=[i for i in result['items'] if access.visible_entity(db,user,'order_items',i['id'])]
        ids={i['id'] for i in result['items']}
        result['notes']=[n for n in result['notes'] if n['entity_id'] in ids]
    elif part=='finance':
        result['items']=[b for b in result['items'] if access.visible_entity(db,user,'order_baselines',b['id'])]
    return result


def service_view(db,user):
    result=_service_view_unscoped(db,user)
    result['projects']=[p for p in result['projects'] if access.visible_project(db,user,p['id'])]
    result['tickets']=[t for t in result['tickets'] if access.visible_entity(db,user,'service_tickets',t['id'])]
    ids={t['id'] for t in result['tickets']}
    result['versions']={key:value for key,value in result['versions'].items() if key in ids}
    result['deliveries']=[d for d in result['deliveries'] if access.visible_project(db,user,d['project_id'])]
    result['procurements']=[p for p in result['procurements'] if p['ticketId'] in ids]
    return result
