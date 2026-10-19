"""Read-only analysis of authorized service records; unknown data stays unknown."""
import json
from aftersales_dashboard import local_date, CLOSED


def text(value):
    return str(value).strip() if isinstance(value, (str,int,float)) else ''


def report(db,user,projects,today):
    deliveries={r['id']:dict(r) for r in db.execute('SELECT l.*,d.project_id,d.delivered_at FROM delivery_lines l JOIN deliveries d ON d.id=l.delivery_id') if r['project_id'] in projects}
    assets={r['serial']:dict(r) for r in db.execute('SELECT * FROM equipment_assets') if r['project_id'] in projects}
    records=[]
    for raw in db.execute('SELECT * FROM service_tickets ORDER BY created_at DESC'):
        r=dict(raw);pid=r['project_id']
        if pid not in projects:continue
        try:p=json.loads(r['payload'])
        except (ValueError,TypeError):continue
        if not isinstance(p,dict):continue
        project=projects[pid]
        delivery=deliveries.get(r['delivery_line_id'],{})
        if delivery.get('project_id')!=pid:delivery={}
        serial=text(p.get('deviceId') or p.get('equipmentSerial'))
        asset=assets.get(serial,{})
        if asset.get('project_id')!=pid:asset={}
        # Neither a delivery quantity nor a product name identifies an individual machine.
        fault=local_date(p.get('faultDate') or p.get('occurrenceDate'))
        feedback=local_date(p.get('date'))
        recorded=fault or feedback
        start=local_date(p.get('activationDate'))
        delivered=local_date(p.get('deliveryDate')) or local_date(delivery.get('delivered_at'))
        repaired=local_date(p.get('lastRepairCompletedDate'))
        root_status=text(p.get('rootCauseStatus'))
        evidence=text(p.get('rootCauseEvidence'))
        root=text(p.get('rootCause') or p.get('causeAnalysis'))
        confirmed=root_status in ('已验证','confirmed') and bool(evidence and root and root!='待确认')
        # The legacy repeated flag is not proof of a recurrence after a completed repair.
        recurrence=bool(fault and repaired and repaired<fault and serial)
        history=p.get('history') if isinstance(p.get('history'),list) else []
        record={'id':r['id'],'project_id':pid,'project':project['name'],
            'model':text(p.get('model') or delivery.get('model_snapshot') or p.get('product')) or '待关联款式',
            'region':text(p.get('region') or project.get('location')) or '待补区域',
            'problem':text(p.get('problemType') or p.get('category')) or '待分类',
            'part':text(p.get('problemPart')) or '待登记部位','description':text(p.get('description')),
            'device':serial,'delivery':delivered,'activation':start,'fault':fault,'feedback':feedback,'date':recorded,
            'date_basis':'故障日期' if fault else '反馈日期' if feedback else '日期待补',
            'repair':repaired,'recurrence':recurrence,'repeat_marked':p.get('repeated')=='是',
            'cause':root if root and root!='待确认' else '原因待排查','cause_status':'已验证' if confirmed else '待验证' if root and root!='待确认' else '排查中',
            'evidence':evidence or '待补现场证据、检验或试验记录',
            'action':text(p.get('correctiveAction') or p.get('solution')) or '待制定整改措施',
            'owner':text(p.get('correctiveOwner') or p.get('owner')) or '待分配',
            'validation':text(p.get('validationResult')) or '尚未登记整改后的验证结果',
            'validation_status':text(p.get('validationStatus')) or '待验证',
            'improvement':text(p.get('suggestion')),'closed':p.get('stage') in CLOSED,
            'shared_test':p.get('source')=='模拟测试' or project.get('notes')=='共享测试项目'}
        records.append(record)
    return {'records':records,'today':today,'year':today[:4],'connection':'售后工作台已接通',
        'notices':['当前包含集团原售后记录与新售后工作台已提交的问题；每条独立问题计一条，登记草稿不计入。',
        '年度与报告按故障日期统计；故障日期未填写时暂按反馈日期，并标明日期来源。两者均缺失的记录不混入期间统计。',
        '首次故障按同一设备全部历史最早故障日期计算；未登记启用日期时仅显示交付后天数，不混入使用时长分布。',
        '维修后复发须具备同一设备编号、故障日期和更早的维修完成日期；原重复标记单独显示，不能当作已核实复发。',
        '未接通完整交付台数、运行时长和对照资料前不计算设备发生率、同比环比或自动确认根因。']}
