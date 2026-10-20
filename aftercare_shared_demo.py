"""Add labelled aftersales tasks to the group's existing shared demo project only."""
import os,json,time
import core,aftercare,aftercare_sync
MARKER='shared_aftersales_tasks_20261020_v1'
def seed(db):
    if os.environ.get('YIFUN_DEMO_MODE')!='1':return False
    if db.execute('SELECT 1 FROM settings WHERE key=?',(MARKER,)).fetchone():return True
    if not db.execute("SELECT 1 FROM settings WHERE key='shared_department_demo_20261014_v2'").fetchone():return False
    project=db.execute("SELECT * FROM projects WHERE id='DEMO-PROJECT-3' AND notes='共享测试项目'").fetchone()
    order=db.execute("SELECT * FROM order_baselines WHERE id='DEMO-FLOW-ORDER-3' AND project_id='DEMO-PROJECT-3'").fetchone()
    owner=db.execute("SELECT * FROM employees WHERE role='admin' AND status='active' ORDER BY created_at,id LIMIT 1").fetchone()
    if not project or not order or not owner:return False
    from datetime import datetime,timedelta
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date();actor=owner['id'];rid=aftercare.internal_request(db,project['id'],actor)
    customer=core.need(db,'customers',project['customer_id'])
    for key,stage,department in [('ENGINEERING','工程下单','工程部'),('PURCHASE','采购','采购部'),('PRODUCTION','生产采购','工厂'),('LOGISTICS','发货物流','物流部'),('INSTALLATION','现场处理','安装服务部')]:
        wid='DEMO-AFTERCARE-'+key
        if db.execute('SELECT 1 FROM af2_customer_work_items WHERE id=?',(wid,)).fetchone() or db.execute('SELECT 1 FROM service_tickets WHERE id=?',(wid,)).fetchone():continue
        d={'id':wid,'workNo':wid,'projectId':project['id'],'customerId':customer['id'],'project':project['name'],'customer':customer['name'],'order':order['number'],'baselineId':order['id'],'product':'共享测试配件 · '+department,'issue':'共享测试售后协同任务（非真实故障）','reported':today.isoformat(),'planned':(today+timedelta(days=3)).isoformat(),'owner':owner['name'],'ownerId':actor,'trackingOwner':owner['name'],'trackingOwnerId':actor,'stage':stage,'department':department,'method':'公司师傅上门','cost':'待确认','grade':'待评估','issueType':'待分类','source':'共享测试','sharedTest':True,'submitted':True,'batchId':'DEMO-AFTERCARE-BATCH','cloudRequestId':rid,'attachments':[],'history':[{'at':today.isoformat(),'actor':owner['name'],'action':'建立集团共用测试任务；非真实售后记录'}],'review':{'approved':True,'method':'共享测试：检查配件并记录处理结果','purchaseItems':'共享测试配件 1 件','needOrder':True,'department':department,'reviewer':owner['name']}}
        if stage not in ('工程下单','采购'):d['engineering']={'confirmed':True,'orderNumber':'DEMO-AF-EO-'+key,'destination':'工厂','engineer':owner['name'],'items':'共享测试配件 1 件','completedAt':today.isoformat()}
        d=aftercare_sync.normalize(db,d)
        db.execute('INSERT INTO af2_customer_work_items VALUES(?,?,?,1,?,?)',(wid,rid,json.dumps(d,ensure_ascii=False),int(time.time()*1000),actor));aftercare.sync_ticket(db,wid,actor)
    db.execute('INSERT INTO settings VALUES(?,?)',(MARKER,core.now()))
    core.audit(db,dict(owner),'demo',MARKER,'建立共用项目的售后协同测试任务',{'project_id':project['id'],'synthetic':True})
    return True
