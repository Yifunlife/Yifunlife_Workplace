"""Additional column restrictions; existing role, project and write guards remain authoritative."""
import json
import core as c

ROLES={'ceo':'CEO','sales':'销售','purchasing':'采购','engineering':'工程','warehouse':'仓库','installation':'安装','aftersales':'售后','finance':'财务','supplier':'供应商'}
GROUPS=[
 ('general','通用工作区',[('dashboard','CEO 总看板'),('tasks','我的待办'),('releases','特殊放行'),('masters','共用档案'),('connections','连接资料'),('migration','数据导入与核对'),('audit','操作记录')]),
 ('marketing','运营中心',[('center-marketing','中心看板'),('center-marketing-spend','投入登记'),('center-marketing-leads','来源线索')]),
 ('crm','销售中心',[('center-crm','销售看板'),('customers','客户档案'),('connections-sales','销售工作台资料'),('leads','线索与跟进'),('opportunities','商机管理'),('center-projects','交付进度'),('orders','订单与变更'),('home','关联业务档案')]),
 ('design','设计中心',[('center-design','设计任务与交接')]),
 ('quote','核算中心',[('center-quote','核算看板'),('quote','报价工作台')]),
 ('engineering','工程中心',[('center-engineering','工程总看板'),('technical','工程下单'),('installation','安装任务'),('issues','现场问题')]),
 ('procurement','采购中心',[('center-procurement','采购总看板（含商务金额）'),('procurement','采购工作台（含订单金额）')]),
 ('factory','生产中心',[('center-factory','生产中心总看板'),('production-wood','木工车间'),('production-upholstery','软包车间'),('production-paint','油漆车间'),('production-metal','铁车间')]),
 ('stock','仓库中心',[('center-stock','中心看板'),('inventory','共用库存'),('warehouse','库存作业'),('counts','盘点管理'),('locations','仓库与库位'),('returns','退换返修')]),
 ('aftersales','售后中心',[('center-aftersales','中心看板'),('center-aftersales-workflow','售后工作台（含内部流程与费用）'),('center-aftersales-issues','问题统计')]),
 ('product_rd','产品研发中心',[('center-product_rd','中心总看板')]),('software','软件中心',[('center-software','中心总看板')]),('brand_visual','品牌视觉中心',[('center-brand_visual','中心总看板')]),
 ('finance','财务中心',[('center-finance','中心看板'),('finance','收款与结算'),('costs','项目成本'),('expenses','费用登记'),('budgets','项目预算')])]
CATALOG={key:label for _,_,pages in GROUPS for key,label in pages}
ALIASES={'center-aftersales':'center-aftersales-workflow','aftersales':'center-aftersales-workflow','center-design-records':'center-design','center-marketing-leads':'leads','quote-entry':'quote'}

def canonical(key):return ALIASES.get(key,key)

def config(db):
    row=db.execute("SELECT value FROM settings WHERE key='column_permissions_v1'").fetchone()
    return json.loads(row[0]) if row else {'version':0,'roles':{},'employees':{}}

def levels(db,user):
    if user['role']=='admin':return {k:2 for k in CATALOG}
    data=config(db);base=data['roles'].get(user['role'],{});own=data['employees'].get(user['id'],{})
    return {key:own.get(canonical(key),base.get(canonical(key),2)) for key in CATALOG}

def level(db,user,key):
    if user['role']=='admin':return 2
    key=canonical(key)
    if key not in CATALOG:return 0
    return levels(db,user)[key]

def require(db,user,key,write=False):
    if level(db,user,key)<(2 if write else 1):raise c.Problem('没有此栏目的操作权限' if write else '没有此栏目的查看权限',403)

def any_read(db,user,keys):
    if not any(level(db,user,k)>0 for k in keys):raise c.Problem('没有此栏目的查看权限',403)

def restricted(db,user):return user['role']!='admin' and any(v<2 for v in levels(db,user).values())

def management(db,user):
    c.permit(user,'admin');data=config(db)
    return {**data,'groups':[{'id':k,'name':n,'pages':[{'id':p,'name':label} for p,label in pages]} for k,n,pages in GROUPS],'role_names':ROLES}

def save(db,user,p):
    c.permit(user,'admin');data=config(db)
    if type(p.get('version')) is not int or p['version']!=data['version']:raise c.Problem('授权已被其他管理员调整，请刷新后重试',409)
    kind=p.get('kind');subject=p.get('subject');grants=p.get('grants')
    if kind not in ('roles','employees') or not isinstance(subject,str) or not isinstance(grants,dict):raise c.Problem('请选择有效的授权对象')
    if kind=='roles':
        if subject not in ROLES:raise c.Problem('管理员权限不可在此修改')
    else:
        target=c.need(db,'employees',subject)
        if target['role']=='admin' or target['id']==user['id']:raise c.Problem('不能在此限制管理员账号')
    if any(k not in CATALOG or canonical(k)!=k or type(v) is not int or v not in (0,1,2) for k,v in grants.items()):raise c.Problem('栏目或权限值无效')
    before=data[kind].get(subject,{})
    data[kind][subject]=grants;data['version']+=1
    db.execute("INSERT INTO settings(key,value) VALUES('column_permissions_v1',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(data,ensure_ascii=False),))
    # Revoke other sessions so stale navigation cannot imply continued permission.
    if kind=='roles':db.execute('DELETE FROM employee_sessions WHERE user_id IN (SELECT id FROM employees WHERE role=?)',(subject,))
    else:db.execute('DELETE FROM employee_sessions WHERE user_id=?',(subject,))
    c.audit(db,user,'column_permissions',subject,'调整角色栏目授权' if kind=='roles' else '调整人员栏目授权',{'before':before,'after':grants,'version':data['version']})
    return {'ok':True,'version':data['version']}

OPS={'engineering':'technical','lookups':None,'leads':'leads'}
def ops_key(page):return OPS.get(page,page)

def core_action(action,p):
    if action in ('customers','projects','project-members'):return 'customers' if action=='customers' else 'home'
    if action in ('products','master-update'):return 'masters'
    if action=='order-from-quote' or action.startswith('change-'):return 'orders'
    if action in ('request-release','decide-release','confirm-deposit'):return 'releases'
    if action=='create-po':return 'procurement'
    if action.startswith('stock-') or action=='deliver':return 'warehouse'
    if action=='finance-entry':return 'finance'
    if action=='technical-review':return 'technical'
    if action.startswith('service-'):return 'center-aftersales-workflow'
    if action=='migration-stage':return 'migration'
    return None

def ops_action(action,p):
    if action in ('save','attach'):return ops_key(p.get('page'))
    if action=='start-quote':return 'quote'
    if action.startswith('engineering-'):return 'technical'
    if action=='warehouse-transfer':return 'warehouse'
    if action.startswith('count-'):return 'counts'
    if action.startswith('return-'):return 'returns'
    if action.startswith('import-'):return 'migration'
    if action=='location-create':return 'locations'
    return None

def center_action(action,p):
    if action in ('members',):return None  # Existing admin-only guard.
    if action=='target':return 'center-'+str(p.get('center',''))
    if action=='followup':return p.get('entity')
    if action in ('snapshot','test_contract'):return 'center-marketing'
    if action=='spend':return 'center-marketing-spend'
    if action.startswith('design'):return 'center-design'
    if action.startswith('engineering'):return 'center-engineering'
    if action.startswith('aftersales'):return 'center-aftersales-workflow'
    return None

def write_guard(db,user,key):
    if key:require(db,user,key,True)
    elif restricted(db,user):raise c.Problem('此操作尚未分配栏目权限',403)


def overview(db,user,result):
    fields={'baselines':'orders','quotations':'quote','releases':'releases','changes':'orders','deliveries':'inventory','service_requests':'center-aftersales-workflow','reservations':'inventory','stock_history':'inventory'}
    for field,key in fields.items():
        if level(db,user,key)==0:result[field]=[]
    # Project/customer IDs and names remain shared reference data, not financial dossiers.
    if level(db,user,'home')==0:
        result['projects']=[{k:v for k,v in row.items() if k in ('id','code','name','customer_id','customer_name')} for row in result.get('projects',[])]
    if level(db,user,'customers')==0:result['customers']=[{k:v for k,v in row.items() if k in ('id','code','name')} for row in result.get('customers',[])]
    if level(db,user,'masters')==0 and level(db,user,'inventory')==0:result['products']=[]
    elif level(db,user,'inventory')==0:
        result['products']=[{k:v for k,v in row.items() if k not in ('on_hand','reserved','unavailable','available')} for row in result.get('products',[])]
    return result
