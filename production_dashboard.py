"""Production overview and four workshop views from authorized engineering records."""
import json
import engineering_dashboard

WORKSHOPS=(('wood','木工车间','木工部'),('upholstery','软包车间','软包部'),('paint','油漆车间','油漆部'),('metal','铁车间','铁车间'))

def report(db,user,projects,today):
    source=engineering_dashboard.report(db,user,projects,today)
    latest={}
    for r in db.execute('SELECT baseline_id,project_id,revision,lines_json FROM engineering_orders ORDER BY revision'):
        if r['project_id'] in projects:latest[r['baseline_id']]=dict(r)
    assigned=set()
    for key,r in latest.items():
        try:lines=json.loads(r['lines_json'])
        except (ValueError,TypeError):lines=[]
        if any(isinstance(line,dict) and line.get('route')=='factory' for line in lines):assigned.add(key)
    rows=[r for r in source['orders'] if r['project_id'] in projects and not r['id'].startswith('future:') and r['stage']!='售后' and (r['stage']=='生产中' or r['id'] in assigned)]
    workshops=[]
    for key,name,dept in WORKSHOPS:
        entries=[]
        for row in rows:
            value=row['progress'].get(dept)
            state='待登记' if value is None else '进度100%' if value==100 else '进行中' if value>0 else '未开始'
            blocked=row['blocker_dept'] in (dept,name)
            entries.append({**row,'workshop_progress':value,'workshop_state':state,'workshop_blocked':blocked})
        workshops.append({'id':key,'name':name,'department':dept,'orders':entries,
            'registered':sum(r['workshop_progress'] is not None for r in entries),
            'unknown':sum(r['workshop_progress'] is None for r in entries),
            'not_started':sum(r['workshop_progress']==0 for r in entries),
            'active':sum(r['workshop_progress'] is not None and 0<r['workshop_progress']<100 for r in entries),
            'complete':sum(r['workshop_progress']==100 for r in entries),'blocked':sum(r['workshop_blocked'] for r in entries)})
    return {'engineering':source,'today':today,'orders':rows,'workshops':workshops,
        'notices':['全周期订单统计与部门进度表共用工程中心数据：总订单按正式订单去重，未来订单单独统计；下方车间汇总仅统计生产执行范围。','汇总授权范围内工程阶段为生产中的正式订单，以及最新工程单中明确分派工厂的订单；按正式订单编号去重，排除未来订单与已转售后订单。',
        '木工、软包、油漆、铁车间进度来自工程中心已登记数据；未登记不等于未开始，也不自动认定该订单一定涉及该车间。',
        '进度100%只代表已登记的工程进度，不替代车间完工、质检或出库确认；各车间订单数不能直接相加作为总订单数。',
        '车间卡点按明确登记的卡点部门识别；负责人显示工程负责人，车间独立派工、排产与质检后续再接通。']}
