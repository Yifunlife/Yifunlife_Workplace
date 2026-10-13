"""Department entry points over shared records; new inputs retain their history."""
import json
from collections import Counter, defaultdict
from datetime import datetime
import core as c
import project_access as access
import operations
import account_reporting
from ceo_dashboard import REPORTING_ZONE, local_day

MANAGERS = ('admin', 'ceo')
CURRENCIES = ('CNY', 'USD', 'EUR', 'SAR', 'AED', 'AUD')
SPEND_CURRENCIES = ('CNY', 'USD', 'EUR', 'SAR', 'AED', 'OTHER')
SPEND_CHANNELS = ('抖音','小红书','视频号','YouTube','阿里巴巴国际站','独立站','Instagram','Facebook','TikTok','展会','其他渠道')
SPEND_EXPENSES = ('广告费','平台服务费','内容制作费','达人合作费','展位费','差旅费','活动物料费','代理服务费','其他费用')
NAMES = {'marketing':'运营中心','crm':'业务中心','design':'设计中心','projects':'项目中心','quote':'报价中心','engineering':'工程中心','procurement':'采购中心','stock':'仓库中心','aftersales':'售后中心','finance':'财务中心','factory':'工厂交接'}
DESIGN_STATES = {'queued':'待排设计','waiting_materials':'待补资料','in_progress':'设计中','review':'内部审核','waiting_confirmation':'待客户确认','revising':'修改中','confirmed':'客户已确认','handoff':'待工程接收','accepted':'工程已接收','cancelled':'已取消'}
TRANSITIONS = {'queued':('waiting_materials','in_progress','cancelled'),'waiting_materials':('queued','in_progress','cancelled'),'in_progress':('review','waiting_confirmation','waiting_materials','cancelled'),'review':('in_progress','waiting_confirmation','revising','cancelled'),'waiting_confirmation':('confirmed','revising','cancelled'),'revising':('review','waiting_confirmation','cancelled'),'confirmed':('handoff','revising'),'handoff':('accepted','revising'),'accepted':(),'cancelled':()}
TARGETS = {'marketing':('spend','月度投入预算','money'),'crm':('booked','月度成交目标','money'),'design':('completed','月度设计确认目标','count'),'projects':('delivered','月度交付批次目标','count'),'engineering':('released','月度工程下单目标','count'),'procurement':('new_orders','月度采购下单目标','count'),'stock':('delivered','月度交付批次目标','count'),'aftersales':('closed','月度售后关闭目标','count')}

def assigned(db,user,center):
    return bool(db.execute('SELECT 1 FROM center_members WHERE employee_id=? AND center=?',(user['id'],center)).fetchone())

def available(db,user):
    role=user['role']
    if role=='supplier':return []
    all_internal = role!='finance'
    flags={'marketing':role in (*MANAGERS,'sales') or assigned(db,user,'marketing'),
           'crm':role in (*MANAGERS,'sales'),
           'design':role in (*MANAGERS,'sales','engineering') or assigned(db,user,'design'),
           'projects':all_internal,'quote':role in (*MANAGERS,'sales'),
           'engineering':all_internal,'procurement':role in (*MANAGERS,'purchasing','engineering','warehouse','finance'),
           'stock':all_internal,'aftersales':all_internal,'finance':True,
           'factory':role in (*MANAGERS,'engineering','purchasing')}
    return [key for key in NAMES if flags[key]]

def require_center(db,user,center):
    if center not in available(db,user):raise c.Problem('没有此中心的使用权限',403)

def event(db,user,entity,key,action,before,after,note=''):
    db.execute('INSERT INTO center_events VALUES(?,?,?,?,?,?,?,?,?)',(c.uid(),entity,key,action,json.dumps(before or {},ensure_ascii=False),json.dumps(after,ensure_ascii=False),note,user['id'],c.now()))
    c.audit(db,user,entity,key,action,{'note':note})

def can_design(db,user):
    return user['role'] in (*MANAGERS,'engineering') or assigned(db,user,'design')

def record(db,user,page,key):
    tables={'spend':'marketing_spends','design':'design_tasks'}
    if page not in tables:raise c.Problem('记录类型无效')
    require_center(db,user,'marketing' if page=='spend' else 'design')
    r=c.need(db,tables[page],key)
    if page=='spend':
        if user['role'] not in MANAGERS and r['owner_id']!=user['id'] and r['created_by']!=user['id']:raise c.Problem('记录不存在或没有权限',404)
        if r['project_id']:access.require(db,user,'projects',r['project_id'])
    else:access.require(db,user,'projects',r['project_id'])
    return r

def records(db,user,page,project=None):
    require_center(db,user,'marketing' if page=='spend' else 'design')
    if project:access.require(db,user,'projects',project)
    table={'spend':'marketing_spends','design':'design_tasks'}.get(page)
    if not table:raise c.Problem('记录类型无效')
    result=[]
    for row in db.execute('SELECT * FROM '+table+' ORDER BY created_at DESC,id'):
        r=dict(row)
        if project and r['project_id']!=project:continue
        try:record(db,user,page,r['id'])
        except c.Problem:continue
        r['events']=[]
        for raw in db.execute('SELECT action,note,actor_id,created_at,before_json,after_json FROM center_events WHERE entity=? AND entity_id=? ORDER BY created_at,rowid',(page,r['id'])):
            entry=dict(raw);before=json.loads(entry.pop('before_json'));after=json.loads(entry.pop('after_json'))
            entry['changes']=history_changes(db,page,before,after)
            r['events'].append(entry)
        result.append(r)
    employees=[dict(r) for r in db.execute("SELECT id,name,role FROM employees WHERE status='active' AND role!='supplier'")]
    if user['role'] not in MANAGERS:
        ids=access.project_ids(db,user)
        employees=[e for e in employees if e['id']==user['id'] or any(access.visible_project(db,e,p) for p in ids)]
    for employee in employees:employee['can_design']=can_design(db,employee)
    return {'items':result,'employees':employees,'can_manage_design':can_design(db,user),'can_write':page=='spend' or user['role'] in (*MANAGERS,'sales') or can_design(db,user)}

def short(value,label,required=False,limit=4000):
    value=str(value or '').strip()
    if len(value)>limit:raise c.Problem(label+'内容过长')
    return c.text(value,label) if required else value

def history_changes(db,page,before,after):
    labels={'record_date':'费用日期','channel':'平台','expense_type':'投入类型','amount_minor':'投入金额','currency':'币种','activity':'活动／账户','region':'地区','reference':'凭证','note':'备注','status':'状态','owner_id':'负责人','project_id':'项目','title':'任务名称','task_type':'任务类型','brief':'需求说明','requested_date':'希望日期','due_date':'承诺日期','original_due_date':'首次承诺','team':'设计组','priority':'优先级','version_label':'成果版本','result_reference':'成果文件位置','revision_count':'修改轮次','confirmation':'客户确认依据','change_reason':'修改原因','handoff_note':'工程交接意见'}
    def display(key,value,snapshot):
        if value is None or value=='':return '—'
        if key=='currency' and value=='OTHER':return '其他币种（详见备注）'
        if key=='amount_minor':return f"{'其他币种' if snapshot.get('currency')=='OTHER' else snapshot.get('currency','')} {value/100:,.2f}"
        if key=='status':return DESIGN_STATES.get(value,value) if page=='design' else {'active':'有效','void':'已作废'}.get(value,value)
        if key=='priority':return {'normal':'正常','urgent':'紧急'}.get(value,value)
        if key in ('owner_id','project_id'):
            row=c.row(db,'SELECT name FROM '+('employees' if key=='owner_id' else 'projects')+' WHERE id=?',(value,))
            return row['name'] if row else str(value)
        return str(value)
    return [{'label':label,'before':display(key,before.get(key),before),'after':display(key,after.get(key),after)} for key,label in labels.items() if key in after and before.get(key)!=after.get(key)]

def execute(db,user,action,p):
    if action=='members':
        c.permit(user,'admin');employee=c.need(db,'employees',p.get('employee_id'))
        if employee['role']=='supplier':raise c.Problem('供应商账号不能分配内部中心职责')
        centers=p.get('centers')
        if not isinstance(centers,list) or any(x not in ('marketing','design') for x in centers) or len(set(centers))!=len(centers):raise c.Problem('请选择有效中心')
        before=[r[0] for r in db.execute('SELECT center FROM center_members WHERE employee_id=?',(employee['id'],))]
        db.execute('DELETE FROM center_members WHERE employee_id=?',(employee['id'],))
        db.executemany('INSERT INTO center_members VALUES(?,?)',[(employee['id'],x) for x in centers])
        event(db,user,'center_members',employee['id'],'分配中心职责',{'centers':before},{'centers':centers})
        return {'ok':True}
    if action=='target':
        c.permit(user,*MANAGERS);center=p.get('center')
        if center not in TARGETS:raise c.Problem('此中心暂无目标指标')
        month=c.day(p.get('month'))
        if not month.endswith('-01'):raise c.Problem('目标月份请选择每月第一天')
        metric,label,kind=TARGETS[center];currency=p.get('currency','CNY') if kind=='money' else ''
        if kind=='money' and currency not in CURRENCIES:raise c.Problem('请选择币种')
        if kind=='money':value=c.money(p.get('value'),zero=True)
        else:
            try:value=int(p.get('value'))
            except (ValueError,TypeError):raise c.Problem('数量目标须为非负整数')
            if value<0:raise c.Problem('数量目标须为非负整数')
        old=c.row(db,'SELECT * FROM center_targets WHERE center=? AND month=? AND metric=? AND currency=?',(center,month,metric,currency))
        if old and old['version']!=p.get('version'):raise c.Problem('目标已调整，请刷新后重试',409)
        key=old['id'] if old else c.uid();stamp=c.now()
        if old:db.execute('UPDATE center_targets SET value=?,version=version+1,updated_at=? WHERE id=?',(value,stamp,key))
        else:db.execute('INSERT INTO center_targets(id,center,month,metric,currency,value,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(key,center,month,metric,currency,value,user['id'],stamp,stamp))
        event(db,user,'target',key,'调整中心目标',old,{'value':value},short(p.get('note'),'调整说明',bool(old)))
        return {'id':key}
    if action=='followup':
        c.permit(user,*MANAGERS,'sales');entity=p.get('entity')
        if entity not in ('leads','opportunities'):raise c.Problem('请选择线索或商机')
        old=operations.get_record(db,user,entity,p.get('entity_id'))
        if old['version']!=p.get('version'):raise c.Problem('业务记录已更新，请刷新后重试',409)
        contact=c.day(p.get('contact_date'));next_date=c.day(p.get('next_date'));result=short(p.get('result'),'沟通结果',True);next_action=short(p.get('next_action'),'下一步',True)
        if next_date<contact:raise c.Problem('下次跟进不能早于本次沟通日期')
        key=c.uid();stamp=c.now()
        db.execute('INSERT INTO crm_followups VALUES(?,?,?,?,?,?,?,?,?)',(key,entity,old['id'],contact,result,next_action,next_date,user['id'],stamp))
        current=c.row(db,'SELECT next_action,next_date FROM crm_followups WHERE entity=? AND entity_id=? ORDER BY contact_date DESC,created_at DESC,rowid DESC LIMIT 1',(entity,old['id']))
        db.execute('UPDATE '+operations.SPECS[entity][0]+' SET next_action=?,'+('next_date=?,' if entity=='leads' else '')+'version=version+1,updated_at=? WHERE id=?',((current['next_action'],current['next_date'],stamp,old['id']) if entity=='leads' else (current['next_action'],stamp,old['id'])))
        event(db,user,entity,old['id'],'记录跟进',old,current,result)
        return {'id':key}
    if action in ('snapshot','test_contract'):return account_reporting.save(db,user,action,p)
    if action=='spend':return save_spend(db,user,p)
    if action=='design':return save_design(db,user,p)
    raise c.Problem('操作不存在',404)

def save_spend(db,user,p):
    require_center(db,user,'marketing')
    old=record(db,user,'spend',p['id']) if p.get('id') else None
    if old and old['version']!=p.get('version'):raise c.Problem('投入记录已更新，请刷新',409)
    if old and old['status']=='void':raise c.Problem('作废记录保留历史，不能再次修改')
    fields={key:short(p.get(key),label,required) for key,label,required in [('channel','平台',True),('expense_type','投入类型',True),('activity','活动或账户',False),('region','推广地区',False),('reference','凭证号',False),('note','备注',False)]}
    if p.get('account_id'):
        account=c.need(db,'marketing_accounts',p['account_id'])
        if fields['channel']!=account['platform']:raise c.Problem('平台与账号不一致')
        fields.update(account_id=account['id'],activity=account['name'])
    date=p.get('record_date')
    if not isinstance(date,str) or len(date)!=10:raise c.Problem('日期请按 yyyy-mm-dd 填写费用实际发生日期')
    fields.update(record_date=c.day(date),amount_minor=c.money(p.get('amount'),zero=True),currency=p.get('currency'),owner_id=c.text(p.get('owner_id'),'负责人'),project_id=p.get('project_id') or None,status=p.get('status','active'))
    for field,options,label in [('channel',SPEND_CHANNELS,'平台'),('expense_type',SPEND_EXPENSES,'投入类型'),('currency',SPEND_CURRENCIES,'币种')]:
        if fields[field] not in options and not (old and fields[field]==old[field]):raise c.Problem('请选择列表中的'+label)
    if fields['status'] not in ('active','void'):raise c.Problem('请选择有效状态')
    if fields['status']=='void' and (not old or not fields['note']):raise c.Problem('作废已有记录时须填写原因')
    if (fields['channel']=='其他渠道' or fields['expense_type']=='其他费用' or fields['currency']=='OTHER') and not fields['note']:raise c.Problem('选择其他渠道、其他费用或其他币种时，必须在备注中写明具体内容')
    owner=c.need(db,'employees',fields['owner_id'])
    if owner['status']!='active' or owner['role']=='supplier':raise c.Problem('请选择有效内部负责人')
    if user['role'] not in MANAGERS and fields['owner_id']!=user['id']:raise c.Problem('只能登记自己负责的投入',403)
    if fields['project_id']:access.require(db,user,'projects',fields['project_id'])
    if old and fields['project_id']!=old['project_id']:raise c.Problem('已有投入不能转移项目；请作废后重新登记')
    if fields.get('account_id'):db.execute('UPDATE marketing_accounts SET owner_id=? WHERE id=?',(fields['owner_id'],fields['account_id']))
    key=old['id'] if old else c.uid();stamp=c.now()
    if old:db.execute('UPDATE marketing_spends SET '+','.join(k+'=?' for k in fields)+',version=version+1,updated_at=? WHERE id=?',(*fields.values(),stamp,key))
    else:
        fields.update(id=key,number=operations.number(db,'marketing_spends','EXP'),created_by=user['id'],created_at=stamp,updated_at=stamp)
        db.execute('INSERT INTO marketing_spends('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(fields.values()))
    event(db,user,'spend',key,'作废投入' if fields['status']=='void' else '更新投入' if old else '登记投入',old,fields,fields['note'])
    return {'id':key}

def save_design(db,user,p):
    require_center(db,user,'design')
    old=record(db,user,'design',p['id']) if p.get('id') else None
    if old and old['version']!=p.get('version'):raise c.Problem('设计任务已更新，请刷新',409)
    editor=can_design(db,user);sales=user['role'] in (*MANAGERS,'sales')
    if not editor and not sales:raise c.Problem('没有编辑设计任务的权限',403)
    project_id=p.get('project_id');access.require(db,user,'projects',project_id)
    if old and old['project_id']!=project_id:raise c.Problem('设计任务不能转移到其他项目')
    fields={key:short(p.get(key),label,required) for key,label,required in [('title','任务名称',True),('task_type','任务类型',True),('brief','需求说明',True),('team','设计组',False),('version_label','成果版本',False),('result_reference','成果文件或链接',False),('confirmation','客户确认依据',False),('change_reason','变更或修改原因',False),('handoff_note','交接意见',False)]}
    fields.update(project_id=project_id,requested_date=c.day(p.get('requested_date')),due_date=c.day(p['due_date']) if p.get('due_date') else None,owner_id=p.get('owner_id') or None,priority=p.get('priority','normal'),status=p.get('status','queued'))
    status=fields['status']
    if status not in DESIGN_STATES or fields['priority'] not in ('normal','urgent'):raise c.Problem('请选择有效状态或优先级')
    if not old and status not in ('queued','waiting_materials'):raise c.Problem('新任务请先提交需求，再安排设计')
    if old and status!=old['status'] and status not in TRANSITIONS[old['status']]:raise c.Problem('不能跳过设计确认或工程接收步骤')
    if old and old['status'] in ('accepted','cancelled'):raise c.Problem('已结束任务保留历史，请新建设计任务')
    if old and not sales and fields['confirmation']!=old['confirmation']:raise c.Problem('客户确认依据由销售维护',403)
    if old and old['status'] in ('confirmed','handoff') and status!='revising' and (fields['result_reference']!=old['result_reference'] or fields['version_label']!=old['version_label']):raise c.Problem('已确认成果需要修改时，请先记录修改原因并进入修改中')
    if fields['owner_id']:
        operations.members_check(db,project_id,fields['owner_id'])
        owner=c.need(db,'employees',fields['owner_id'])
        if not can_design(db,owner):raise c.Problem('设计负责人须具有工程岗位或设计中心职责')
    if not editor:
        if old and (fields['owner_id']!=old['owner_id'] or fields['due_date']!=old['due_date']):raise c.Problem('排期与设计负责人由设计人员安排',403)
        if not old and (fields['owner_id'] or fields['due_date']):raise c.Problem('先提交需求，由设计人员接单排期')
        if old and status!=old['status'] and status not in ('confirmed','revising','cancelled'):raise c.Problem('销售可记录客户确认、修改反馈或取消',403)
        if old and (fields['result_reference']!=old['result_reference'] or fields['version_label']!=old['version_label']):raise c.Problem('成果版本由设计人员提交',403)
    if status not in ('queued','waiting_materials','cancelled') and (not fields['owner_id'] or not fields['due_date']):raise c.Problem('开始设计前请指定设计师及承诺日期')
    if status in ('waiting_confirmation','confirmed','handoff','accepted') and (not fields['version_label'] or not fields['result_reference']):raise c.Problem('请先填写成果版本及文件链接或文件位置')
    if status=='confirmed' and (not old or old['status']!='confirmed'):
        if not sales:raise c.Problem('客户确认由销售记录',403)
        if not fields['confirmation']:raise c.Problem('请填写客户确认依据')
    if status=='accepted' and user['role'] not in (*MANAGERS,'engineering'):raise c.Problem('请由工程人员确认接收',403)
    if status=='accepted' and not fields['handoff_note']:raise c.Problem('请填写工程接收意见')
    if status in ('revising','cancelled') and not fields['change_reason']:raise c.Problem('请填写修改或取消原因')
    if old and old['due_date'] and old['due_date']!=fields['due_date'] and not fields['change_reason']:raise c.Problem('调整承诺日期须填写原因；首次承诺保留不变')
    stamp=c.now();key=old['id'] if old else c.uid()
    fields['original_due_date']=(old['original_due_date'] if old else None) or fields['due_date']
    fields['revision_count']=(old['revision_count'] if old else 0)+(1 if old and status=='revising' and old['status']!='revising' else 0)
    fields['completed_at']=(old['completed_at'] if old else None)
    if status=='revising':fields['completed_at']=None;fields['confirmation']=''
    elif status=='confirmed' and not fields['completed_at']:fields['completed_at']=stamp
    fields['accepted_at']=stamp if status=='accepted' else None
    if old:db.execute('UPDATE design_tasks SET '+','.join(k+'=?' for k in fields)+',version=version+1,updated_at=? WHERE id=?',(*fields.values(),stamp,key))
    else:
        fields.update(id=key,number=operations.number(db,'design_tasks','DS'),created_by=user['id'],created_at=stamp,updated_at=stamp)
        db.execute('INSERT INTO design_tasks('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(fields.values()))
    event(db,user,'design',key,DESIGN_STATES[status] if not old or old['status']!=status else '更新设计任务',old,fields,fields['change_reason'] or fields['handoff_note'])
    return {'id':key}

def dashboard(db,user,center,start=None,end=None,project=None,currency='CNY'):
    require_center(db,user,center)
    today=datetime.now(REPORTING_ZONE).date().isoformat()
    start=c.day(start) if start else today[:8]+'01';end=c.day(end) if end else today
    if start>end:raise c.Problem('开始日期不能晚于结束日期')
    if currency not in CURRENCIES and not (center=='marketing' and currency=='OTHER'):raise c.Problem('请选择币种')
    if project:access.require(db,user,'projects',project)
    in_period=lambda v:bool(v and local_day(v) and start<=local_day(v).isoformat()<=end)
    # Date-only business fields are already local calendar dates.
    in_day=lambda v:bool(v and start<=v[:10]<=end)
    scoped=lambda r:access.visible_project(db,user,r['project_id']) and (not project or r['project_id']==project)
    employees={r['id']:r['name'] for r in db.execute('SELECT id,name FROM employees')}
    projects={r['id']:dict(r) for r in db.execute('SELECT * FROM projects') if access.visible_project(db,user,r['id']) and (not project or r['id']==project)}
    metrics=[];rows=[];groups=[];notices=[];sales=None
    def metric(key,label,value,unit='项',hint='截至今天'):
        metrics.append({'key':key,'label':label,'value':value,'unit':unit,'hint':hint})
    def item(r,title,status,page,detail='',due=None,owner=None):
        rows.append({'id':r['id'],'title':title,'status':status,'page':page,'project_id':r.get('project_id'),'project_name':projects.get(r.get('project_id'),{}).get('name',''),'detail':detail,'due':due,'owner':owner or employees.get(r.get('owner_id'),'待分配')})
    if center=='marketing':
        spends=[r for r in records(db,user,'spend',project)['items'] if r['status']=='active' and r['currency']==currency and in_day(r['record_date'])]
        leads=operations.list_rows(db,user,'leads')
        if project:
            lead_ids={r[0] for r in db.execute('SELECT lead_id FROM crm_opportunities WHERE project_id=?',(project,))}
            leads=[r for r in leads if r['id'] in lead_ids]
        period_leads=[r for r in leads if in_period(r['created_at'])]
        metric('spend','本期登记投入',None if currency=='OTHER' else sum(r['amount_minor'] for r in spends),'money','其他币种请按备注逐笔核对，不合计' if currency=='OTHER' else '按费用发生日 · '+currency)
        if currency=='OTHER':metrics[-1]['empty_text']='逐笔查看'
        metric('leads','本期新增线索',len(period_leads),'条','按线索创建日')
        metric('qualified','其中有效线索',sum(r['status']=='qualified' for r in period_leads),'条','本期新增线索的当前判断')
        metric('pending','其中待判断',sum(r['status'] in ('new','contacting') for r in period_leads),'条','由销售跟进后判断')
        for channel in sorted({r['channel'] for r in spends}|{r['source'] for r in period_leads}):
            subset=[r for r in period_leads if r['source']==channel]
            groups.append({'label':channel,'amount':None if currency=='OTHER' else sum(r['amount_minor'] for r in spends if r['channel']==channel),'count':len(subset),'qualified':sum(r['status']=='qualified' for r in subset)})
        for r in leads:
            if r['status'] not in ('lost',) and r['next_date']<today:item(r,r['name'],'跟进已逾期','leads',r['next_action'],r['next_date'])
        notices=['投入仅汇总所选币种；这是运营登记，未计入财务费用账。','渠道表并列展示本期投入与新增线索，尚不计算跨月归因投产比。']
        if currency=='OTHER':notices.append('其他币种可能包含不同货币，不计算合计或统一预算；请到投入登记按备注核对原币金额。')
    elif center=='crm':
        leads=operations.list_rows(db,user,'leads');opps=operations.list_rows(db,user,'opportunities')
        if project:opps=[r for r in opps if r['project_id']==project];leads=[r for r in leads if r['id'] in {o['lead_id'] for o in opps}]
        orders=[dict(r) for r in db.execute('SELECT * FROM order_baselines') if scoped(r) and (user['role'] in MANAGERS or r['created_by']==user['id'])]
        metric('booked','本期确认订单金额',sum(r['agreed_minor'] for r in orders if r['currency']==currency and in_period(r['created_at'])),'money','原单及增项 · '+currency)
        metric('opportunities','在跟商机',sum(r['stage'] not in ('won','lost') for r in opps),'个')
        metric('qualified','有效线索',sum(r['status']=='qualified' for r in leads),'条')
        metric('followups','本期跟进记录',sum(in_day(r['contact_date']) for r in db.execute('SELECT * FROM crm_followups') if (r['entity']=='leads' and r['entity_id'] in {x['id'] for x in leads}) or (r['entity']=='opportunities' and r['entity_id'] in {x['id'] for x in opps})),'次','按沟通日期')
        groups=[{'label':label,'count':sum(r['stage']==stage for r in opps)} for stage,label in [('discovery','需求沟通'),('solution','方案确认'),('quotation','报价中'),('negotiation','商务洽谈'),('won','已成交'),('lost','已终止')]]
        for r in leads:
            if r['status']!='lost' and r['next_date']<=today:item(r,r['name'],'今日应跟进' if r['next_date']==today else '跟进已逾期','leads',r['next_action'],r['next_date'])
        for r in opps:
            if r['stage'] not in ('won','lost'):
                follow=c.row(db,"SELECT next_date FROM crm_followups WHERE entity='opportunities' AND entity_id=? ORDER BY contact_date DESC,created_at DESC,rowid DESC LIMIT 1",(r['id'],))
                item(r,r['name'],'商机待跟进' if follow else '预计成交待推进','opportunities',r['next_action'],follow['next_date'] if follow else r['expected_date'])
        notices=['阶段分布是当前商机数量，不作为同批商机转化率。','成交金额读取正式订单，商机预估金额不计入业绩；回款由财务确认。']
        import connections
        shared=connections.status(db,user,project)
        if shared['enabled']:
            metric('shared_customers','销售工作台客户',len(shared['sales']),'位','按当前项目权限')
            notices.append('销售工作台客户及跟进信息请在“销售工作台资料”查看；未转换成内部线索或商机，不重复计算业绩。')
        customers={r['id']:dict(r) for r in db.execute('SELECT * FROM customers')}
        quotes=[dict(r) for r in db.execute("SELECT * FROM quotation_history WHERE archived_at IS NULL AND voided_at IS NULL ORDER BY generated_at DESC") if r['project_id'] in projects and (user['role'] in MANAGERS or r['created_by']==user['email'])]
        sales_projects=[]
        for pid,p in projects.items():
            own=[q for q in quotes if q['project_id']==pid]
            signed=[o for o in orders if o['project_id']==pid]
            latest=own[0] if own else None
            stage='已签单' if signed else '已报价待签单' if latest and latest['is_finalized'] else '报价中' if latest else '设计中'
            sales_projects.append({'id':pid,'code':p['code'],'name':p['name'],'customer':customers.get(p['customer_id'],{}).get('name','待补充'),'owner':p['owner'] or '待分配','stage':stage,'quote_minor':round(float(latest['final_amount'])*100) if latest and latest['final_amount'] is not None else None,'quote_currency':latest['final_currency'] if latest else None,'contract_minor':sum(o['agreed_minor'] for o in signed if o['currency']==currency) if signed else None})
        funnel=[{'label':label,'count':sum(p['stage']==label for p in sales_projects),'amount':sum((p['quote_minor'] or 0) for p in sales_projects if p['stage']==label and p['quote_currency']==currency)} for label in ('设计中','报价中','已报价待签单','已签单')]
        annual_start=end[:4]+'-01-01'
        annual_orders=[o for o in orders if o['currency']==currency and local_day(o['created_at']) and annual_start<=local_day(o['created_at']).isoformat()<=end]
        metric('annual_booked','年度合同金额',sum(o['agreed_minor'] for o in annual_orders),'money',annual_start+' 至 '+end+' · 含增项 · '+currency)
        metric('signed_projects','本期签单项目',len({o['project_id'] for o in orders if in_period(o['created_at'])}),'个','项目去重，增项不重复计数')
        import sales_dashboard
        sales_lifecycle=sales_dashboard.report(db,user,projects,orders,quotes,start,end,today)
        sales={'lifecycle':sales_lifecycle,'funnel':funnel,'projects':sales_projects,'period_contract_count':sum(in_period(o['created_at']) for o in orders),'annual_contract_count':len(annual_orders)}
        notices.append('销售项目阶段沿用共用报价及正式订单：无有效报价归入设计中，已确认报价且未签单归入待签单；设计任务实际执行请查看设计中心。')
    elif center=='design':
        tasks=records(db,user,'design',project)['items'];active=[r for r in tasks if r['status'] not in ('accepted','cancelled')]
        due=[r for r in tasks if r['status']!='cancelled' and in_day(r['original_due_date'])]
        timely=[r for r in due if r['completed_at'] and local_day(r['completed_at']).isoformat()<=r['original_due_date']]
        metric('queued','待排／待资料',sum(r['status'] in ('queued','waiting_materials') for r in tasks),'项')
        metric('active','设计处理中',sum(r['status'] in ('in_progress','review','revising') for r in tasks),'项')
        metric('completed','本期客户确认',sum(in_period(r['completed_at']) for r in tasks),'项','按客户确认日期')
        metric('on_time','首次承诺准时率',round(len(timely)*100/len(due),1) if due else None,'%','按本期首次承诺应交任务；含未完成')
        if not due:metrics[-1]['empty_text']='暂无应交任务'
        metric('handoff','待工程接收',sum(r['status']=='handoff' for r in tasks),'项')
        groups=[{'label':label,'count':sum(r['status']==status for r in tasks)} for status,label in DESIGN_STATES.items()]
        for r in active:item(r,r['title'],DESIGN_STATES[r['status']],'center-design-records',r['number']+' · '+(r['version_label'] or '尚未提交版本')+' · 修改 '+str(r['revision_count'])+' 轮',r['due_date'])
        notices=['设计提交、客户确认、工程接收分别记录；调整排期保留首次承诺及原因。']
    elif center=='quote':
        quotes=[dict(r) for r in db.execute('SELECT * FROM quotation_history') if (scoped(r) if r['project_id'] else user['role'] in MANAGERS and not project) and (user['role'] in MANAGERS or r['created_by']==user['email']) and not r['archived_at'] and not r['voided_at']]
        metric('created','本期报价记录',sum(in_period(r['generated_at']) for r in quotes),'份','按生成日；包含修订记录')
        metric('draft','待成交确认',sum(not r['is_finalized'] and not r['ordered_at'] for r in quotes),'份')
        metric('confirmed','已确认待下单',sum(bool(r['is_finalized']) and not r['ordered_at'] for r in quotes),'份')
        metric('ordered','已转正式订单',sum(bool(r['ordered_at']) for r in quotes),'份')
        for r in quotes:
            if not r['ordered_at']:item(r,r['contract_no'] or r['project_name'],'已确认待下单' if r['is_finalized'] else '待成交确认','quote',r['project_name'],owner=r['created_by'])
        notices=['报价编辑、产品库、历史记录继续使用原报价工作台。报价记录数不等于客户数或成交数。']
        import connections
        shared=connections.status(db,user,project)
        if shared['enabled']:
            metric('online_quotes','线上报价记录',sum(in_period(r['generated_at']) for r in shared['quotes']),'份','线上原始记录，含修订与归档；不计作正式订单')
            for r in shared['quotes']:
                item(r,r['contract_no'],'已作废' if r['voided_at'] else '已归档' if r['archived_at'] else '已确认' if r['is_finalized'] else '未确认','connections',r['project_name'],owner=r['created_by'])
            notices.append('线上报价通过固定编号关联；本地订单与线上报价分开统计，避免重复计算。')
    elif center in ('engineering','factory'):
        engineering=operations.list_rows(db,user,'engineering',project)
        if center=='factory':engineering=[r for r in engineering if any(x['route']=='factory' for x in r['lines'])]
        metric('draft','待下达工程单',sum(r['status']=='draft' for r in engineering),'份')
        metric('released','本期下达工程单',sum(r['status']=='released' and in_period(r['released_at']) for r in engineering),'份','按下达日期')
        tasks=[dict(r) for r in db.execute('SELECT * FROM work_tasks') if scoped(r)]
        if center=='engineering':
            metric('installation','待完成安装',sum(r['kind']=='installation' and r['status']!='accepted' for r in tasks),'项')
            metric('issues','未关闭现场问题',sum(r['kind']=='issue' and r['status']!='closed' for r in tasks),'项')
            handoffs=[dict(r) for r in db.execute("SELECT * FROM design_tasks WHERE status='handoff'") if scoped(r)]
            metric('design_handoffs','设计成果待接收',len(handoffs),'项')
            for r in handoffs:item(r,r['title'],'设计成果待工程接收','center-design-records',r['number']+' · '+r['version_label'],r['due_date'])
        for r in engineering:item(r,r['number'],'已下达' if r['status']=='released' else '待下达','technical',str(len(r['lines']))+' 项执行明细',r['required_date'],employees.get(r['created_by']))
        if center=='engineering':
            for r in tasks:
                if r['kind'] in ('installation','issue') and r['status'] not in ('accepted','closed'):item(r,r['title'],'现场待处理','installation' if r['kind']=='installation' else 'issues',r['description'],r['due_date'])
        else:notices=['这里只追踪已有工程单中的工厂执行去向。生产排程、完工和质检尚未接入，不显示模拟生产进度。']
    elif center=='procurement':
        orders=[dict(r) for r in db.execute('SELECT p.*,x.project_id FROM purchase_orders p LEFT JOIN procurement_context x ON x.order_id=p.id WHERE p.archived_at IS NULL') if access.visible_order(db,user,r['id']) and (not project or r['project_id']==project)]
        quantities={r['order_id']:dict(r) for r in db.execute('SELECT order_id,SUM(quantity) quantity,SUM(shipped_quantity) shipped,SUM(received_quantity) received,SUM(stocked_quantity) stocked FROM order_items GROUP BY order_id')}
        metric('new_orders','本期采购订单',sum(in_day(r['order_date']) for r in orders),'份','按采购日期')
        metric('active','未全部入库订单',sum(quantities.get(r['id'],{}).get('quantity',0)>quantities.get(r['id'],{}).get('stocked',0) for r in orders),'份')
        overdue=0
        for r in orders:
            q=quantities.get(r['id'],{});due=r['promised_ship_date'] or r['required_ship_date'];remaining=q.get('quantity',0)-q.get('shipped',0)
            late=bool(due and due<today and remaining>0);overdue+=late
            if q.get('quantity',0)>q.get('stocked',0):item(r,r['po_number'],'发货逾期' if late else '采购执行中','procurement','发货 '+str(q.get('shipped',0))+' / 收货 '+str(q.get('received',0))+' / 入库 '+str(q.get('stocked',0)),due,r['purchaser_name'])
        metric('overdue','发货逾期',overdue,'份')
        notices=['采购、供应商确认、发货和验收沿用原采购工作台；备货订单不强制关联项目。']
    elif center=='stock':
        inventory=c.inventory(db)
        if project:
            product_ids={r[0] for r in db.execute('SELECT DISTINCT l.product_id FROM baseline_lines l JOIN order_baselines b ON b.id=l.baseline_id WHERE b.project_id=?',(project,))}
            inventory=[r for r in inventory if r['id'] in product_ids]
        metric('stocked_skus','有库存产品',sum(r['on_hand']>0 for r in inventory),'种','产品种数，不累加不同计量单位')
        metric('held','有占用产品',sum(r['reserved']>0 for r in inventory),'种')
        metric('quarantine','待检／不可用产品',sum(r['unavailable']>0 for r in inventory),'种')
        deliveries=[dict(r) for r in db.execute('SELECT * FROM deliveries') if scoped(r)]
        metric('delivered','本期交付批次',sum(in_day(r['delivered_at']) for r in deliveries),'批','按实际交付日')
        for r in inventory:
            if r['unavailable']>0 or r['reserved']>0:item(r,r['sku']+' · '+r['name'],'有待检库存' if r['unavailable'] else '项目已占用','inventory','在库 '+str(r['on_hand'])+' / 占用 '+str(r['reserved'])+' / 可用 '+str(r['available'])+' '+r['unit'])
        notices=['库存来自共用账本。选定项目时显示该项目相关产品的全仓余额，不代表该项目独占数量。']
    elif center=='aftersales':
        tickets=[dict(r) for r in db.execute('SELECT * FROM service_tickets') if scoped(r)]
        open_count=closed=overdue=0
        for r in tickets:
            payload=json.loads(r['payload']);stage=payload.get('stage') or '接收反馈';due=payload.get('dueDate')
            if stage=='关闭与复盘':closed+=in_period(r['updated_at']);continue
            open_count+=1;late=bool(due and due<today);overdue+=late
            item(r,payload.get('product') or r['id'],'处理逾期' if late else stage,'aftersales',payload.get('description',''),due,payload.get('owner'))
        metric('new','本期新增工单',sum(in_period(r['created_at']) for r in tickets),'单','按创建日');metric('open','未关闭工单',open_count,'单');metric('closed','本期关闭状态更新',closed,'单','当前已关闭且本期有更新；非首次关闭次数');metric('overdue','逾期工单',overdue,'单')
        notices=['工单、设备保修和退换返修共用项目及实际交付资料。关闭指标按现有工单更新时间统计。']
    elif center=='projects':
        tasks=[dict(r) for r in db.execute('SELECT * FROM work_tasks') if scoped(r)]
        designs=[dict(r) for r in db.execute('SELECT * FROM design_tasks') if scoped(r)]
        metric('projects','可见项目',len(projects),'个');metric('pending','未完成项目事项',sum(r['status'] not in ('done','accepted','closed') for r in tasks),'项')
        metric('designs','待设计／交接',sum(r['status'] not in ('accepted','cancelled') for r in designs),'项')
        deliveries=[dict(r) for r in db.execute('SELECT * FROM deliveries') if scoped(r)]
        metric('delivered','本期交付批次',sum(in_day(r['delivered_at']) for r in deliveries),'批','按实际交付日')
        for r in projects.values():
            open_tasks=[t for t in tasks if t['project_id']==r['id'] and t['status'] not in ('done','accepted','closed')]
            item({**r,'project_id':r['id']},r['code']+' · '+r['name'],'有逾期事项' if any(t['due_date']<today for t in open_tasks) else '项目进行中','home',str(len(open_tasks))+' 项待处理',owner=employees.get(r.get('owner_id')))
    elif center=='finance':
        enabled=c.setting(db,'finance_enabled')=='1'
        notices=['财务功能暂未开放。收款、应收及利润不使用零值代替尚未接入的数据。'] if not enabled else ['按所选币种展示；成本资料未齐时不计算利润。']
        entries=[]
        if enabled and user['role'] in (*MANAGERS,'finance'):
            orders={r['id']:dict(r) for r in db.execute('SELECT * FROM order_baselines') if scoped(r) and r['currency']==currency}
            entries=[dict(r) for r in db.execute('SELECT * FROM customer_financial_entries') if r['baseline_id'] in orders]
            balances=[r['agreed_minor']+sum(e['amount_minor']*(1 if e['kind']=='surcharge' else -1) for e in entries if e['baseline_id']==r['id']) for r in orders.values()]
            remaining=sum(max(value,0) for value in balances)
            metric('receipts','本期确认回款',sum(r['amount_minor'] for r in entries if r['kind']=='receipt' and in_day(r['record_date'])),'money',currency)
            metric('remaining','当前应收余额',remaining,'money',currency)
            if any(value<0 for value in balances):metric('excess','超收待核对',sum(-value for value in balances if value<0),'money','不抵扣其他订单应收 · '+currency)
        else:
            metric('receipts','本期确认回款',None,'money','暂未开放或无查看权限');metric('remaining','当前应收余额',None,'money','暂未开放或无查看权限')
    target=None
    if center in TARGETS and currency!='OTHER' and user['role'] in MANAGERS and not project and start.endswith('-01') and start[:7]==end[:7]:
        key,label,kind=TARGETS[center]
        target=c.row(db,'SELECT * FROM center_targets WHERE center=? AND month=? AND currency=?',(center,start,currency if kind=='money' else ''))
        target={'definition':{'metric':key,'label':label,'kind':kind},'record':target,'actual':next((m['value'] for m in metrics if m['key']==key),None)}
    rows.sort(key=lambda r:(r['due'] or '9999',r['title']))
    account_report=account_reporting.report(db,start,end,today,currency) if center=='marketing' and user['role'] in MANAGERS else None
    return {'account_reporting':account_report,'sales':sales,'center':center,'title':NAMES[center],'metrics':metrics,'rows':rows,'groups':groups,'notices':notices,'target':target,'period':{'from':start,'to':end},'today':today,'currency':currency,'updated_at':c.now(),'can_manage':user['role'] in MANAGERS}
