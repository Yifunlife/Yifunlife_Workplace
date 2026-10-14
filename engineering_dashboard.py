"""Authorized order-level engineering progress. Missing values stay unknown."""
import json
from datetime import date
import core as c
import project_access as access

STAGES = ('未排期','下单中','生产中','待安装','安装中','售后','未来订单')
DEPTS = ('下单','木工部','软包部','油漆部','铁车间','采购部','安装')


def save(db, user, p):
    c.permit(user, 'admin', 'ceo', 'engineering')
    project = access.require(db, user, 'projects', p.get('project_id'))
    key = c.text(p.get('id'), '订单编号')
    if key.startswith('future:'):
        if key != 'future:' + project['id'] or db.execute('SELECT 1 FROM order_baselines WHERE project_id=?',(project['id'],)).fetchone():
            raise c.Problem('预计订单已转正式订单，请刷新',409)
    else:
        order = access.require(db, user, 'order_baselines', key)
        if order['project_id'] != project['id']: raise c.Problem('订单与项目不匹配')
    old = db.execute('SELECT * FROM engineering_tracking WHERE id=?',(key,)).fetchone()
    if (old['version'] if old else 0) != p.get('version'): raise c.Problem('记录已更新，请刷新',409)
    stage = p.get('stage')
    if stage not in STAGES or (key.startswith('future:')) != (stage=='未来订单'): raise c.Problem('请选择有效订单阶段')
    owner = p.get('owner_id') or None
    if owner:
        employee = c.need(db,'employees',owner)
        if employee['status']!='active' or employee['role'] not in ('engineering','admin','ceo'):raise c.Problem('请选择有效工程负责人')
        if employee['role']=='engineering' and not access.visible_project(db,employee,project['id']):raise c.Problem('负责人须加入对应项目')
    due = c.day(p['delivery_date']) if p.get('delivery_date') else None
    values = p.get('progress',{})
    if not isinstance(values,dict) or set(values)-set(DEPTS): raise c.Problem('无效部门进度')
    progress = {}
    for dept in DEPTS:
        value = values.get(dept)
        if value in ('',None):progress[dept]=None;continue
        try: number = int(value)
        except (ValueError,TypeError): raise c.Problem('进度须为0至100的整数')
        if str(number)!=str(value) or not 0<=number<=100:raise c.Problem('进度须为0至100的整数')
        progress[dept]=number
    blocker = str(p.get('blocker_dept') or '')
    if blocker and blocker not in DEPTS+('工程部','设计部','核算部','商务部','安装部','其他'):raise c.Problem('请选择卡点部门')
    reason = str(p.get('blocker_reason') or '').strip()[:2000]
    if blocker and not reason:raise c.Problem('请填写卡点原因')
    issue = str(p.get('issue') or '').strip()[:4000]
    payload = (project['id'], stage, owner, due, json.dumps(progress,ensure_ascii=False), blocker, reason, issue, user['id'],c.now())
    if old:
        db.execute('UPDATE engineering_tracking SET project_id=?,stage=?,owner_id=?,delivery_date=?,progress_json=?,blocker_dept=?,blocker_reason=?,issue=?,updated_by=?,updated_at=?,version=version+1 WHERE id=?',(*payload,key))
    else:
        db.execute('INSERT INTO engineering_tracking(project_id,stage,owner_id,delivery_date,progress_json,blocker_dept,blocker_reason,issue,updated_by,updated_at,id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(*payload,key))
    c.audit(db,user,'engineering_tracking',key,'更新工程进度及问题反馈',{'before':dict(old) if old else None,'after':dict(db.execute('SELECT * FROM engineering_tracking WHERE id=?',(key,)).fetchone())})
    return {'ok':True}


def report(db,user,projects,today):
    employees={r['id']:dict(r) for r in db.execute('SELECT * FROM employees')}
    by_email={r['email']:r['name'] for r in employees.values()}
    tracking={r['id']:dict(r) for r in db.execute('SELECT * FROM engineering_tracking') if r['project_id'] in projects}
    orders=[dict(r) for r in db.execute('SELECT * FROM order_baselines') if r['project_id'] in projects]
    signed={r['project_id'] for r in orders}
    # One anticipated row per authorized project until a formal order exists.
    orders += [{'id':'future:'+p['id'],'project_id':p['id'],'number':p['code']} for p in projects.values() if p['id'] not in signed]
    output=[]
    for order in orders:
        pid=order['project_id'];project=projects[pid];meta=tracking.get(order['id'],{})
        future=order['id'].startswith('future:')
        engineering=db.execute('SELECT * FROM engineering_orders WHERE baseline_id=? ORDER BY revision DESC LIMIT 1',(order['id'],)).fetchone()
        stage=meta.get('stage') or ('未来订单' if future else '下单中' if engineering else '未排期')
        def owners(role):
            return '、'.join(employees.get(r[0],{}).get('name','待分配') for r in db.execute('SELECT employee_id FROM project_members WHERE project_id=? AND assignment_role=?',(pid,role)))
        design=db.execute("SELECT owner_id FROM design_tasks WHERE project_id=? AND status!='cancelled' ORDER BY updated_at DESC LIMIT 1",(pid,)).fetchone()
        quote=db.execute('SELECT created_by FROM quotation_history WHERE id=?',(order.get('quote_id'),)).fetchone()
        owner=meta.get('owner_id') or (engineering['created_by'] if engineering else None)
        progress=json.loads(meta.get('progress_json') or '{}')
        if engineering and engineering['status']=='released' and progress.get('下单') is None:progress['下单']=100
        due=meta.get('delivery_date');days=(date.fromisoformat(due)-date.fromisoformat(today)).days if due else None
        output.append({'shared_test':project.get('notes')=='共享测试项目','id':order['id'],'project_id':pid,'name':project['name'],'number':order['number'],'stage':stage,
            'sales_owner':owners('owner') or project.get('owner') or '待分配','design_owner':employees.get(design['owner_id'],{}).get('name','待分配') if design else '待分配',
            'costing_owner':by_email.get(quote['created_by'],'待核对') if quote else '待分配','engineering_owner':employees.get(owner,{}).get('name','待分配'),
            'owner_id':owner,'delivery_date':due,'days':days,'progress':progress,'blocker_dept':meta.get('blocker_dept',''),'blocker_reason':meta.get('blocker_reason',''),
            'issue':meta.get('issue',''),'version':meta.get('version',0)})
    alerts=sorted([r for r in output if r['stage'] not in ('未来订单','售后') and r['days'] is not None and r['days']<=10],key=lambda r:r['days'])
    return {'orders':output,'alerts':alerts,'today':today,'can_edit':user['role'] in ('admin','ceo','engineering'),
        'employees':[{'id':r['id'],'name':r['name']} for r in employees.values() if r['status']=='active' and r['role'] in ('admin','ceo','engineering') and (r['role'] in ('admin','ceo') or any(access.visible_project(db,r,pid) for pid in projects))],
        'notices':['正式订单按订单编号去重，包含安装中及售后订单；未来订单为尚无正式订单的授权项目，单独统计。',
        '各部门百分比、交货期与卡点来自工程登记；未登记显示待登记，不以工程要求日期替代交货期，不自动推断责任部门。',
        '下单进度可从已下达工程单读取100%；其它百分比由负责人核实登记。进度登记不代替正式工程下单、采购或安装验收。',
        '距交货期10天以内及已逾期的未交付订单进入重点提醒；完成整体验收后须转入售后阶段。']}
