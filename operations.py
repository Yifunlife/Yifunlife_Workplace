import object_storage
"""Project-linked operational pages. All writes use the existing database transaction."""
import base64
import hashlib
import json
import math
from datetime import date
import core as c
import project_access as access

MANAGERS = ('admin', 'ceo')
INTERNAL = ('admin','ceo','sales','purchasing','engineering','warehouse','installation','aftersales','finance')
SPECS = {
    'tasks': ('work_tasks', ('admin','ceo','sales','purchasing','engineering','warehouse','installation','aftersales'), ('project_id','title','owner_id','due_date','status','description','location','blocking','resolution','acceptance')),
    'installation': ('work_tasks', ('engineering','installation'), ('project_id','title','owner_id','due_date','status','description','location','blocking','resolution','acceptance')),
    'issues': ('work_tasks', ('engineering','installation','purchasing','warehouse','aftersales','sales'), ('project_id','title','owner_id','due_date','status','description','location','blocking','resolution','acceptance')),
    'equipment': ('equipment_assets', ('installation','engineering','aftersales'), ('project_id','delivery_line_id','serial','name','location','warranty_start','warranty_end','notes')),
    'leads': ('crm_leads', ('admin','ceo','sales'), ('name','company','contact','phone','source','owner_id','status','next_date','next_action','notes','customer_id','region','activity','validity_reason','customer_grade')),
    'opportunities': ('crm_opportunities', ('sales',), ('lead_id','customer_id','project_id','name','owner_id','stage','expected_minor','currency','expected_date','next_action','notes')),
    'expenses': ('project_expenses', ('finance','ceo'), ('project_id','category','amount_minor','currency','record_date','reference','note')),
    'budgets': ('project_budgets', ('finance','ceo'), ('project_id','currency','amount_minor','note')),
}
KINDS = {'tasks':'task','installation':'installation','issues':'issue'}
STATES = {'tasks':('planned','in_progress','blocked','done'), 'installation':('planned','in_progress','awaiting_acceptance','accepted'), 'issues':('open','in_progress','resolved','closed'), 'leads':('new','contacting','qualified','lost'), 'opportunities':('discovery','solution','quotation','negotiation','won','lost')}
EXTRA_TABLES = {'engineering':'engineering_orders','returns':'return_cases','counts':'stock_counts','locations':'warehouse_locations','warehouse':'warehouse_operations'}

def number(db, table, prefix):
    return f'{prefix}-{date.today():%Y%m%d}-{db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]+1:04d}'

def finite(value, zero=False):
    try: result=float(value)
    except (TypeError,ValueError): raise c.Problem('请填写有效数量')
    if not math.isfinite(result) or result < 0 or (not zero and result == 0): raise c.Problem('数量须为有效正数')
    return result

def project_check(db,user,key):
    return access.require(db,user,'projects',key)

def allowed(db,user,page,r):
    if page=='leads':
        import centers
        return user['role'] in MANAGERS or (user['role']=='sales' and r['owner_id']==user['id']) or (centers.assigned(db,user,'marketing') and (r['created_by']==user['id'] or r['owner_id']==user['id']))
    if page in ('leads','opportunities'):
        return user['role'] in MANAGERS or (user['role']=='sales' and r['owner_id']==user['id'] and (not r.get('project_id') or access.visible_project(db,user,r['project_id'])))
    if page in ('locations','warehouse','counts'):
        return user['role'] in (*MANAGERS,'warehouse','purchasing','engineering','aftersales')
    return access.visible_project(db,user,r['project_id'])

def get_record(db,user,page,key):
    table=SPECS[page][0] if page in SPECS else EXTRA_TABLES.get(page)
    if not table: raise c.Problem('页面不存在',404)
    r=c.need(db,table,key)
    if not allowed(db,user,page,r): raise c.Problem('记录不存在或没有查看权限',404)
    if page in KINDS and r['kind']!=KINDS[page]: raise c.Problem('记录类型不一致',404)
    if page in ('expenses','budgets'):
        c.permit(user,'finance','ceo','admin')
        if page=='expenses': c.finance_access(db,user)
    return r

def members_check(db,project_id,owner):
    e=c.need(db,'employees',owner)
    if e['status']!='active' or e['role']=='supplier' or not access.visible_project(db,e,project_id):
        raise c.Problem('负责人须为该项目的有效成员')

def list_rows(db,user,page,project=None):
    table=SPECS[page][0] if page in SPECS else EXTRA_TABLES[page]
    result=[]
    for item in db.execute('SELECT * FROM '+table):
        r=dict(item)
        if page in KINDS and r['kind']!=KINDS[page]:continue
        if not allowed(db,user,page,r) or (project and r.get('project_id') and r['project_id']!=project):continue
        if page=='tasks' and user['role'] not in MANAGERS and r['owner_id']!=user['id'] and r['created_by']!=user['id']:continue
        if page=='engineering':
            r['lines']=json.loads(r.pop('lines_json'))
            r['purchases']=[dict(p) for p in db.execute('SELECT p.id,p.po_number,p.status,COALESCE(SUM(i.quantity),0) quantity,COALESCE(SUM(i.received_quantity),0) received,COALESCE(SUM(i.stocked_quantity),0) stocked FROM engineering_purchase_links x JOIN purchase_orders p ON p.id=x.order_id LEFT JOIN order_items i ON i.order_id=p.id WHERE x.engineering_id=? AND p.archived_at IS NULL GROUP BY p.id',(r['id'],))]
        r['files']=[dict(f) for f in db.execute('SELECT id,file_name,mime,created_at FROM operation_files WHERE entity=? AND entity_id=? ORDER BY created_at',(page,r['id']))]
        result.append(r)
    return sorted(result,key=lambda x:x.get('created_at',''),reverse=True)

def balance(db,product,location):
    return db.execute('SELECT COALESCE(SUM(quantity),0) FROM stock_movements WHERE product_id=? AND location_id=?',(product,location)).fetchone()[0]

def fingerprint(db,product,location):
    rows=db.execute('SELECT id,quantity FROM stock_movements WHERE product_id=? AND location_id=? ORDER BY rowid',(product,location)).fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()

def stock_move(db,user,product,location,quantity,kind,reference,note):
    c.need(db,'products',product);c.need(db,'warehouse_locations',location)
    if balance(db,product,location)+quantity < -1e-6:raise c.Problem('该库位库存不足，请核对库位或拆分数量')
    key=c.uid()
    db.execute('INSERT INTO stock_movements(id,product_id,quantity,kind,reference_id,note,actor_id,created_at,location_id) VALUES(?,?,?,?,?,?,?,?,?)',(key,product,quantity,kind,reference,note,user['id'],c.now(),location))
    return key

def unreserved(db,product,quantity):
    available=c.inventory_one(db,product)
    if available[0]-available[1]+quantity < -1e-6:raise c.Problem('操作后可用库存不足，已有客户或售后占用')

def view(db,user,page,project=None):
    c.permit(user,*INTERNAL)
    if project:project_check(db,user,project)
    import centers
    marketing=centers.assigned(db,user,'marketing')
    if page=='opportunities' or (page=='leads' and not marketing):c.permit(user,*MANAGERS,'sales')
    if page in ('warehouse','counts','locations'):c.permit(user,*MANAGERS,'warehouse','purchasing','engineering','aftersales')
    if page in ('costs','expenses','budgets'):c.permit(user,*MANAGERS,'finance')
    if page=='expenses' and c.setting(db,'finance_enabled')!='1':return {'items':[],'enabled':False,'can_write':False}
    if page=='expenses':c.finance_access(db,user)
    if page=='costs':return costs(db,user,project)
    if page=='lookups':
        projects=[dict(r) for r in db.execute('SELECT p.id,p.code,p.name FROM projects p') if access.visible_project(db,user,r['id'])]
        ids={p['id'] for p in projects}
        employees=[dict(r) for r in db.execute("SELECT id,name,role FROM employees WHERE status='active' AND role!='supplier'") if user['role'] in MANAGERS or r['id']==user['id'] or any(access.visible_project(db,dict(r),p) for p in ids)]
        deliveries=[dict(r) for r in db.execute('SELECT l.*,d.project_id,d.number FROM delivery_lines l JOIN deliveries d ON d.id=l.delivery_id') if r['project_id'] in ids]
        if marketing:
            employees=list({e['id']:e for e in [*employees,*[dict(r) for r in db.execute("SELECT id,name,role FROM employees WHERE status='active' AND role='sales'")]]}.values())
        return {'employees':employees,'deliveries':deliveries,'locations':[dict(r) for r in db.execute('SELECT * FROM warehouse_locations ORDER BY warehouse,code')], 'leads':list_rows(db,user,'leads') if user['role'] in (*MANAGERS,'sales') or marketing else [],'enabled':c.setting(db,'finance_enabled')=='1'}
    if page not in SPECS and page not in EXTRA_TABLES:raise c.Problem('页面不存在',404)
    result={'items':list_rows(db,user,page,project),'can_write':user['role'] in (SPECS[page][1] if page in SPECS else {'engineering':('engineering',),'returns':('sales','aftersales','installation','warehouse','purchasing'),'warehouse':('warehouse',),'counts':('warehouse',),'locations':('admin','warehouse')}[page]),'enabled':True}
    if page=='leads' and marketing:result['can_write']=True
    if page in ('leads','opportunities'):
        for item in result['items']:
            item['latest_followup']=c.row(db,'SELECT contact_date,result,next_action,next_date FROM crm_followups WHERE entity=? AND entity_id=? ORDER BY contact_date DESC,created_at DESC,rowid DESC LIMIT 1',(page,item['id']))
    if page=='tasks':
        related=[]
        for key in ('installation','issues'):
            for task in list_rows(db,user,key,project):
                if task['status'] not in ('accepted','closed') and (user['role'] in MANAGERS or task['owner_id']==user['id']):
                    related.append({'title':task['title'],'project_id':task['project_id'],'owner_id':task['owner_id'],'due_date':task['due_date'],'page':key})
        if user['role'] in (*MANAGERS,'engineering'):
            for b in db.execute("SELECT id,project_id,number FROM order_baselines WHERE NOT EXISTS (SELECT 1 FROM engineering_orders e WHERE e.baseline_id=order_baselines.id AND e.status='released')"):
                if access.visible_project(db,user,b['project_id']) and (not project or project==b['project_id']):
                    related.append({'title':'待编制或下达工程单 · '+b['number'],'project_id':b['project_id'],'owner_id':None,'due_date':None,'page':'technical'})
        if 'design' in centers.available(db,user):
            for task in centers.records(db,user,'design',project)['items']:
                if task['status'] not in ('accepted','cancelled') and (user['role'] in MANAGERS or user['id'] in (task['owner_id'],task['created_by']) or (user['role']=='engineering' and task['status']=='handoff')):
                    related.append({'title':centers.DESIGN_STATES[task['status']]+' · '+task['title'],'project_id':task['project_id'],'owner_id':task['owner_id'],'due_date':task['due_date'],'page':'center-design-records'})
        result['related']=related
    if page=='warehouse':
        result['balances']=[dict(r) for r in db.execute('SELECT m.product_id,m.location_id,p.name,p.sku,p.unit,l.warehouse,l.name location_name,l.usable,SUM(m.quantity) quantity FROM stock_movements m JOIN products p ON p.id=m.product_id JOIN warehouse_locations l ON l.id=m.location_id GROUP BY m.product_id,m.location_id HAVING ABS(SUM(m.quantity))>0.000001 ORDER BY l.warehouse,p.sku')]
    return result

def save(db,user,page,p):
    import centers
    table,roles,fields=SPECS[page]
    marketing=page=='leads' and centers.assigned(db,user,'marketing')
    if not marketing:c.permit(user,*roles)
    if page=='expenses':c.finance_access(db,user)
    old=get_record(db,user,page,p['id']) if p.get('id') else None
    if old and p.get('version')!=old['version']:raise c.Problem('记录已被其他人修改，请刷新后重试',409)
    if old and page=='expenses':raise c.Problem('费用凭证保留原记录，请联系财务核对')
    values={key:p.get(key,'') for key in fields}
    if page=='opportunities' and old:
        values['project_id']=p.get('project_id',old['project_id'])
        if old['project_id'] and values['project_id']!=old['project_id']:raise c.Problem('已关联报价的商机不能更换项目')
    optional={'notes','description','location','resolution','acceptance','phone','note','project_id','customer_id','blocking','expected_minor','region','activity','validity_reason','customer_grade'}
    for key in fields:
        if key not in optional and key not in ('amount_minor',):values[key]=c.text(values[key],key)
        if isinstance(values[key],str) and len(values[key])>10000:raise c.Problem('单个字段内容过长')
    if 'project_id' in values:
        if not values['project_id'] and page!='opportunities':raise c.Problem('请选择关联项目')
        if values['project_id']:project_check(db,user,values['project_id'])
        else:values['project_id']=None
    if old and old.get('project_id')!=values.get('project_id') and page!='opportunities':raise c.Problem('已有记录不能转移到其他项目')
    if values.get('owner_id'):
        if values.get('project_id'):members_check(db,values['project_id'],values['owner_id'])
        elif user['role']=='sales' and values['owner_id']!=user['id']:raise c.Problem('销售只能维护自己负责的线索或商机',403)
    for key in ('due_date','next_date','expected_date','warranty_start','warranty_end','record_date'):
        if key in values:values[key]=c.day(values[key])
    if page in STATES:
        field='stage' if page=='opportunities' else 'status'
        if values[field] not in STATES[page]:raise c.Problem('请选择有效状态')
    if page in KINDS:
        values['blocking']=1 if str(values['blocking']) in ('1','true') else 0
        if values['status'] in ('resolved','closed') and not str(values['resolution']).strip():raise c.Problem('请填写问题处理结果')
        if page=='issues' and values['status']=='closed' and old and user['id']!=old['created_by']:raise c.Problem('请由现场提交人确认问题已解决后关闭',403)
        if page=='installation' and values['status']=='accepted':
            if not str(values['acceptance']).strip():raise c.Problem('请填写客户验收签收记录')
            if db.execute("SELECT 1 FROM work_tasks WHERE project_id=? AND kind='issue' AND blocking=1 AND status!='closed'",(values['project_id'],)).fetchone():raise c.Problem('仍有影响安装的现场问题未关闭')
        values['kind']=KINDS[page]
    if page=='equipment':
        delivery=access.require(db,user,'delivery_lines',values['delivery_line_id']);parent=c.need(db,'deliveries',delivery['delivery_id'])
        if parent['project_id']!=values['project_id']:raise c.Problem('设备必须关联该项目的实际交付产品')
        if values['warranty_end']<values['warranty_start']:raise c.Problem('保修结束日期不能早于开始日期')
    if page=='leads':
        values['customer_grade']=p.get('customer_grade',old.get('customer_grade','') if old else '')
        if values['customer_grade'] not in ('','A','B','C'):raise c.Problem('请选择 A、B、C 客户标签')
        if values['customer_grade']!=(old.get('customer_grade','') if old else '') and user['role'] not in MANAGERS and not marketing:raise c.Problem('客户标签由运营部维护',403)
        owner=c.need(db,'employees',values['owner_id'])
        if owner['status']!='active' or owner['role']=='supplier':raise c.Problem('请选择有效内部负责人')
        if marketing and user['role'] not in MANAGERS and owner['id']!=user['id'] and owner['role']!='sales':raise c.Problem('线索请交给销售或自己跟进')
        values['customer_id']=values['customer_id'] or None
        if values['customer_id']:access.require(db,user,'customers',values['customer_id'])
    if page=='opportunities':
        lead=get_record(db,user,'leads',values['lead_id']);access.require(db,user,'customers',values['customer_id'])
        if lead['owner_id']!=values['owner_id']:raise c.Problem('商机负责人须与线索负责人一致')
        if values['project_id'] and c.need(db,'projects',values['project_id'])['customer_id']!=values['customer_id']:raise c.Problem('商机客户与项目客户不一致')
        values['expected_minor']=c.money(values['expected_minor'],zero=True) if values['expected_minor'] not in ('',None) else None
    if 'amount_minor' in values:values['amount_minor']=c.money(values['amount_minor'],zero=page=='budgets')
    if values.get('currency') not in (None,'CNY','USD'):raise c.Problem('请选择币种')
    if page=='expenses' and values['category'] not in ('freight','installation','travel','rework','aftersales','other'):raise c.Problem('请选择费用类别')
    key=old['id'] if old else c.uid();stamp=c.now()
    if page in KINDS:
        terminal={'tasks':'done','installation':'accepted','issues':'closed'}[page]
        values['completed_at']=(stamp if not old or old['status']!=terminal else old.get('completed_at')) if values['status']==terminal else None
    if old:
        db.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in values)+',version=version+1,updated_at=? WHERE id=?',(*values.values(),stamp,key))
    else:
        values.update(id=key,created_by=user['id'],created_at=stamp,updated_at=stamp)
        db.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
    if page=='leads' and (marketing or user['role'] in MANAGERS) and (not old or old['owner_id']!=values['owner_id']) and owner['role']=='sales':
        db.execute('INSERT INTO marketing_lead_allocations VALUES(?,?,?,?,?)',(c.uid(),key,owner['id'],user['id'],stamp))
    c.audit(db,user,page,key,'更新记录' if old else '新建记录',{'project_id':values.get('project_id')})
    if page in ('leads','opportunities'):centers.event(db,user,page,key,'更新业务阶段' if old else '建立业务记录',old,values)
    return {'id':key}

def engineering(db,user,action,p):
    c.permit(user,'engineering')
    if action=='engineering-save':
        b=access.require(db,user,'order_baselines',p.get('baseline_id'))
        old=get_record(db,user,'engineering',p['id']) if p.get('id') else None
        if old and (old['status']!='draft' or old['version']!=p.get('version')):raise c.Problem('工程单已下达或已更新，请刷新',409)
        if old and old['baseline_id']!=b['id']:raise c.Problem('不能更换工程单关联的销售订单')
        supplied=p.get('lines',[]);expected=[c.baseline_effective(db,dict(r)) for r in db.execute('SELECT * FROM baseline_lines WHERE baseline_id=? ORDER BY line_order',(b['id'],))]
        if not isinstance(supplied,list) or {x.get('id') for x in supplied}!={r['id'] for r in expected} or len(supplied)!=len(expected):raise c.Problem('工程单须包含销售订单全部明细')
        items=[]
        for r in expected:
            item=next(x for x in supplied if x['id']==r['id'])
            if item.get('route') not in ('purchase','factory'):raise c.Problem('请选择采购或工厂执行')
            items.append({'id':r['id'],'product_id':r['effective_product_id'],'name':r['name'],'sku':r['sku'],'quantity':r['effective_quantity'],'model':r['effective_model'],'specification':c.text(item.get('specification'),'执行规格'),'route':item['route'],'drawing':str(item.get('drawing',''))[:2000]})
        revision=db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM engineering_orders WHERE baseline_id=?',(b['id'],)).fetchone()[0]
        key=old['id'] if old else c.uid();values=(c.day(p.get('required_date')),str(p.get('notes',''))[:10000],json.dumps(items,ensure_ascii=False))
        if old:db.execute('UPDATE engineering_orders SET required_date=?,notes=?,lines_json=?,version=version+1 WHERE id=?',(*values,key))
        else:db.execute('INSERT INTO engineering_orders(id,project_id,baseline_id,number,revision,required_date,notes,lines_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,b['project_id'],b['id'],number(db,'engineering_orders','EO'),revision,*values,user['id'],c.now()))
    else:
        old=get_record(db,user,'engineering',p.get('id'));key=old['id']
        if old['status']!='draft' or old['version']!=p.get('version'):raise c.Problem('工程单已更新，请刷新',409)
        if db.execute("SELECT 1 FROM order_changes o JOIN baseline_lines l ON l.id=o.baseline_line_id WHERE l.baseline_id=? AND o.status IN ('draft','confirmed')",(old['baseline_id'],)).fetchone():raise c.Problem('订单存在待处理变更，请先完成销售确认及变更处理')
        for item in json.loads(old['lines_json']):
            line=c.baseline_effective(db,c.need(db,'baseline_lines',item['id']))
            if (item['product_id'],item['quantity'],item['model'])!=(line['effective_product_id'],line['effective_quantity'],line['effective_model']):raise c.Problem('销售订单需求已变化，请更新工程单')
        db.execute("UPDATE engineering_orders SET status='released',released_by=?,released_at=?,version=version+1 WHERE id=?",(user['id'],c.now(),key))
    c.audit(db,user,'engineering',key,'下达工程单' if action=='engineering-release' else '保存工程单',{})
    return {'id':key}

def purchase_engineering(db,user,baseline,items):
    order=c.row(db,"SELECT * FROM engineering_orders WHERE baseline_id=? AND status='released' ORDER BY revision DESC LIMIT 1",(baseline['id'],))
    if not order:raise c.Problem('请等待工程下达工程单，再建立项目采购单',403)
    lines={x['id']:x for x in json.loads(order['lines_json'])}
    for item in items:
        line=lines.get(item.get('baselineLineId'))
        effective=c.baseline_effective(db,c.need(db,'baseline_lines',item.get('baselineLineId')))
        if not line or line['route']!='purchase':raise c.Problem('此产品尚未由工程分派采购执行')
        if (line['product_id'],line['quantity'],line['model'])!=(effective['effective_product_id'],effective['effective_quantity'],effective['effective_model']):raise c.Problem('工程单与最新销售需求不一致，请工程修订后再采购')
        item['specification']=line['specification']
    return order['id']

def warehouse(db,user,action,p):
    c.permit(user,'warehouse')
    product=c.need(db,'products',p.get('product_id'));key=c.uid();stamp=c.now()
    if action=='count-create':
        location=c.need(db,'warehouse_locations',p.get('location_id'))
        db.execute('INSERT INTO stock_counts(id,product_id,location_id,expected,counted,fingerprint,reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(key,product['id'],location['id'],balance(db,product['id'],location['id']),finite(p.get('counted'),True),fingerprint(db,product['id'],location['id']),c.text(p.get('reason'),'盘点说明'),user['id'],stamp))
    else:
        source=c.need(db,'warehouse_locations',p.get('source_id'));destination=c.need(db,'warehouse_locations',p.get('destination_id'))
        qty=finite(p.get('quantity'));note=c.text(p.get('note'),'调拨说明')
        if source['id']==destination['id']:raise c.Problem('调出与调入库位不能相同')
        if source['usable'] and not destination['usable']:unreserved(db,product['id'],-qty)
        if balance(db,product['id'],source['id'])<qty-1e-6:raise c.Problem('调出库位库存不足')
        stock_move(db,user,product['id'],destination['id'],qty,'transfer_in',key,note)
        stock_move(db,user,product['id'],source['id'],-qty,'transfer_out',key,note)
        db.execute('INSERT INTO warehouse_operations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,number(db,'warehouse_operations','WH'),'transfer',product['id'],source['id'],destination['id'],qty,str(p.get('reference','')),note,user['id'],stamp))
    c.audit(db,user,'warehouse',key,'建立盘点单' if action=='count-create' else '确认库位调拨',{})
    return {'id':key}

def post_count(db,user,p):
    c.permit(user,'warehouse');r=get_record(db,user,'counts',p.get('id'))
    if r['status']!='draft' or p.get('version')!=r['version']:raise c.Problem('盘点单已更新或已入账',409)
    if r['fingerprint']!=fingerprint(db,r['product_id'],r['location_id']):raise c.Problem('盘点期间库存已发生变化，请重新盘点',409)
    delta=r['counted']-r['expected']
    if c.need(db,'warehouse_locations',r['location_id'])['usable']:unreserved(db,r['product_id'],delta)
    if abs(delta)>1e-6:stock_move(db,user,r['product_id'],r['location_id'],delta,'count',r['id'],r['reason'])
    db.execute("UPDATE stock_counts SET status='posted',posted_by=?,version=version+1 WHERE id=?",(user['id'],r['id']))
    c.audit(db,user,'count',r['id'],'核对盘点差异并入账',{'difference':delta});return {'ok':True}

def returns(db,user,action,p):
    if action=='return-create':
        c.permit(user,'sales','aftersales','installation');project_check(db,user,p.get('project_id'))
        line=access.require(db,user,'delivery_lines',p.get('delivery_line_id'))
        if c.need(db,'deliveries',line['delivery_id'])['project_id']!=p['project_id']:raise c.Problem('交付记录与项目不一致')
        qty=finite(p.get('quantity'));used=db.execute("SELECT COALESCE(SUM(quantity),0) FROM return_cases WHERE delivery_line_id=? AND status!='cancelled'",(line['id'],)).fetchone()[0]
        if qty+used>line['quantity']+1e-6:raise c.Problem('退换数量超过尚未退换的实际交付数量')
        kind=p.get('kind');replacement=p.get('replacement_product_id') or None
        if kind not in ('return','exchange','repair'):raise c.Problem('请选择处理类型')
        if kind=='exchange':c.need(db,'products',replacement)
        key=c.uid();stamp=c.now()
        db.execute('INSERT INTO return_cases(id,project_id,delivery_line_id,kind,quantity,reason,replacement_product_id,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,p['project_id'],line['id'],kind,qty,c.text(p.get('reason'),'原因'),replacement,user['id'],stamp,stamp))
    else:
        r=get_record(db,user,'returns',p.get('id'));key=r['id']
        if r['version']!=p.get('version'):raise c.Problem('退换单已更新，请刷新',409)
        if action=='return-confirm':
            c.permit(user,'sales')
            if r['status']!='requested':raise c.Problem('当前状态不能重复确认')
            db.execute("UPDATE return_cases SET status='confirmed',sales_by=?,responsibility=?,version=version+1,updated_at=? WHERE id=?",(user['id'],c.text(p.get('responsibility'),'责任与差额处理说明'),c.now(),key))
        elif action=='return-receive':
            c.permit(user,'warehouse')
            if r['status']!='confirmed':raise c.Problem('须先由销售确认，且不能重复收货')
            location=c.need(db,'warehouse_locations',p.get('location_id'))
            if location['usable']:raise c.Problem('退回产品请先放入待检或不良品库位')
            line=c.need(db,'delivery_lines',r['delivery_line_id'])
            stock_move(db,user,line['product_id'],location['id'],r['quantity'],'return',key,r['reason'])
            db.execute("UPDATE return_cases SET status='received',location_id=?,received_by=?,received_at=?,version=version+1,updated_at=? WHERE id=?",(location['id'],user['id'],c.now(),c.now(),key))
        elif action=='return-close':
            c.permit(user,'aftersales','purchasing')
            if r['status']!='received':raise c.Problem('请先完成实物收货与处置')
            db.execute("UPDATE return_cases SET status='closed',resolution=?,version=version+1,updated_at=? WHERE id=?",(c.text(p.get('resolution'),'实物处置及补发凭证'),c.now(),key))
        else:raise c.Problem('操作不存在',404)
    c.audit(db,user,'return',key,action,{});return {'id':key}

def costs(db,user,project):
    items=[]
    for r in db.execute('SELECT id,code,name FROM projects'):
        if not access.visible_project(db,user,r['id']) or (project and project!=r['id']):continue
        for currency in ('CNY','USD'):
            purchase=db.execute('SELECT COALESCE(SUM(i.amount),0) FROM order_items i JOIN purchase_orders o ON o.id=i.order_id JOIN procurement_context x ON x.order_id=o.id WHERE x.project_id=? AND o.archived_at IS NULL',(r['id'],)).fetchone()[0] if currency=='CNY' else 0
            sales=db.execute('SELECT COALESCE(SUM(agreed_minor),0) FROM order_baselines WHERE project_id=? AND currency=?',(r['id'],currency)).fetchone()[0]
            budget=c.row(db,'SELECT * FROM project_budgets WHERE project_id=? AND currency=?',(r['id'],currency))
            expenses=db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM project_expenses WHERE project_id=? AND currency=?',(r['id'],currency)).fetchone()[0] if c.setting(db,'finance_enabled')=='1' else None
            if not (purchase or sales or budget or expenses) and currency=='USD':continue
            items.append({**dict(r),'currency':currency,'purchase_minor':round(purchase*100),'sales_minor':sales,'budget':budget,'expenses_minor':expenses,'profit_minor':None})
    return {'items':items,'enabled':c.setting(db,'finance_enabled')=='1','can_write':user['role'] in ('finance','ceo')}

def attach(db,user,p):
    page=p.get('page');r=get_record(db,user,page,p.get('id'))
    if page=='engineering' and r['status']!='draft':raise c.Problem('已下达工程单的附件不可替换，请新建修订')
    roles=SPECS[page][1] if page in SPECS else {'engineering':('engineering',),'returns':('aftersales','sales','warehouse','installation','purchasing')}.get(page,())
    c.permit(user,*roles)
    if page=='expenses':c.finance_access(db,user)
    try:content=base64.b64decode(p.get('content',''),validate=True)
    except Exception:raise c.Problem('附件内容无效')
    if not 0<len(content)<=5*1024*1024:raise c.Problem('每个附件须小于 5 MB')
    mime=p.get('mime','application/octet-stream')
    if mime not in ('image/png','image/jpeg','image/webp','application/pdf','application/octet-stream','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.openxmlformats-officedocument.wordprocessingml.document'):raise c.Problem('请上传照片、PDF 或 Office 文件')
    key=c.uid();object_key=f'operations/{page}/{key}'
    object_storage.put(object_key,content,mime)
    db.execute('INSERT INTO operation_files(id,entity,entity_id,file_name,mime,content,created_by,created_at,object_key) VALUES(?,?,?,?,?,?,?,?,?)',(key,page,r['id'],c.text(p.get('file_name'),'文件名')[:200],mime,b'',user['id'],c.now(),object_key))
    c.audit(db,user,page,r['id'],'追加附件',{'attachment_id':key});return {'id':key}

def file(db,user,key):
    r=c.need(db,'operation_files',key);get_record(db,user,r['entity'],r['entity_id'])
    r['content']=object_storage.get(r['object_key']) if r.get('object_key') else r['content']
    return r

def imports(db,user,action,p):
    c.permit(user,'admin')
    kind=p.get('kind');source=c.text(p.get('source'),'来源系统／批次');raw=p.get('rows')
    if kind not in ('customers','projects','products') or not isinstance(raw,list) or not 1<=len(raw)<=500:raise c.Problem('请选择档案类型，每批须为 1 至 500 条')
    items=[];prepared=[];seen=set();identifier='sku' if kind=='products' else 'code'
    for i,original in enumerate(raw):
        if not isinstance(original,dict):raise c.Problem('文件格式不正确')
        row={str(k):str(v).strip() for k,v in original.items()};code=row.get(identifier,'');name=row.get('name','');old=None;error=''
        if not code or not name:error='编号和名称必填'
        elif code.lower() in seen:error='本批编号重复'
        else:
            seen.add(code.lower());matches=[dict(r) for r in db.execute(f'SELECT * FROM {kind} WHERE lower(trim({identifier}))=lower(?)',(code,))]
            if len(matches)>1:error='原档案有多个同编号记录，须人工核对'
            elif matches:old=matches[0]
        payload={identifier:code,'name':name}
        if kind=='customers':payload.update({k:row.get(k,'') for k in ('contact','phone','email','notes')})
        if kind=='products':
            payload.update(unit=row.get('unit',''),specification=row.get('specification',''))
            if not payload['unit']:error=error or '计量单位必填'
        if kind=='projects':
            customer=c.row(db,'SELECT id FROM customers WHERE code=?',(row.get('customer_code',''),))
            if not customer:error=error or '客户编号不存在，请先导入客户'
            payload.update(customer_id=customer['id'] if customer else None,location=row.get('location',''),notes=row.get('notes',''))
            if row.get('owner_email'):
                owner=c.row(db,"SELECT id FROM employees WHERE email=? COLLATE NOCASE AND status='active' AND role!='supplier'",(row['owner_email'],))
                if not owner:error=error or '负责人账号不存在或已停用'
                else:payload['owner_id']=owner['id']
        if old:
            for key,value in payload.items():
                if key=='owner_id':continue
                if str(old.get(key,'') or '')!=str(value or ''):error=error or '编号已存在且内容不同，请人工核对，不覆盖原记录'
        status='需修正' if error else '已有，保留' if old else '待新增'
        items.append({'row':i+2,'code':code,'name':name,'status':status,'message':error or ('不重复建立档案' if old else '核对通过')})
        prepared.append((payload,old))
    digest=hashlib.sha256(json.dumps({'kind':kind,'source':source,'rows':raw,'result':items},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    result={'items':items,'ready':all(i['status']!='需修正' for i in items),'digest':digest}
    if action=='import-preview':return result
    if not result['ready'] or p.get('digest')!=digest:raise c.Problem('资料或现有档案已变化，请重新核对后再导入',409)
    imported=0
    for payload,old in prepared:
        target=old['id'] if old else c.execute(db,user,kind,payload)['id']
        if not old:imported+=1
        record=c.row(db,'SELECT id,target_id FROM legacy_records WHERE source_system=? AND source_environment=? AND entity_type=? AND legacy_id=?',('csv',source,kind,payload[identifier]))
        if record and record['target_id'] not in (None,target):raise c.Problem('旧编号已关联到其他档案，请人工核对',409)
        if not record:db.execute('INSERT INTO legacy_records(id,source_system,source_environment,entity_type,legacy_id,raw_json,status,target_id,imported_at) VALUES(?,?,?,?,?,?,?,?,?)',(c.uid(),'csv',source,kind,payload[identifier],json.dumps(payload,ensure_ascii=False),'imported',target,c.now()))
    c.audit(db,user,'import',source,'核对后导入档案',{'kind':kind,'imported':imported,'skipped':len(prepared)-imported})
    return {'imported':imported,'skipped':len(prepared)-imported}

def execute(db,user,action,p):
    c.permit(user,*INTERNAL)
    if action=='start-quote':
        c.permit(user,'sales')
        if p.get('opportunity_id'):
            opportunity=get_record(db,user,'opportunities',p['opportunity_id'])
            if opportunity['project_id']:
                project_check(db,user,opportunity['project_id'])
                return {'id':opportunity['project_id']}
            project_id=c.execute(db,user,'projects',{'customer_id':opportunity['customer_id'],'name':opportunity['name']})['id']
            db.execute('UPDATE crm_opportunities SET project_id=?,version=version+1,updated_at=? WHERE id=?',(project_id,c.now(),opportunity['id']))
            c.audit(db,user,'opportunities',opportunity['id'],'从商机开始报价',{'project_id':project_id})
            return {'id':project_id}
        return c.execute(db,user,'projects',{key:p[key] for key in ('name','customer_id','new_customer') if key in p})
    if action=='save' and p.get('page') in SPECS:return save(db,user,p['page'],p)
    if action in ('engineering-save','engineering-release'):return engineering(db,user,action,p)
    if action in ('warehouse-transfer','count-create'):return warehouse(db,user,action,p)
    if action=='count-post':return post_count(db,user,p)
    if action.startswith('return-'):return returns(db,user,action,p)
    if action=='attach':return attach(db,user,p)
    if action in ('import-preview','import-commit'):return imports(db,user,action,p)
    if action=='location-create':
        c.permit(user,'admin','warehouse');key=c.uid()
        if p.get('category') not in ('purchase','parts','factory_toy','factory_material'):raise c.Problem('请选择库存范围')
        db.execute('INSERT INTO warehouse_locations VALUES(?,?,?,?,?,?)',(key,c.text(p.get('code'),'库位编号'),c.text(p.get('warehouse'),'仓库名称'),c.text(p.get('name'),'库位名称'),p['category'],0 if str(p.get('usable'))=='0' else 1))
        c.audit(db,user,'location',key,'建立仓库库位',{});return {'id':key}
    raise c.Problem('操作不存在',404)
