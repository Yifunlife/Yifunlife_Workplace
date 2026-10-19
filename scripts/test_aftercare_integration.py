import os,sys,tempfile,json,base64,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.environ.update(YIFUN_CONTAINER_MODE='0',YIFUN_PUBLIC_ORIGIN='',YIFUN_DATABASE_BACKEND='local',YIFUN_DEMO_MODE='0',YIFUN_DATA_ROOT=tempfile.mkdtemp(prefix='aftercare-qa-'),YIFUN_NODE=os.environ.get('YIFUN_NODE') or shutil.which('node') or '/Users/markfang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
sys.path.insert(0,str(root))
import workplace,database,core,aftercare,aftersales_analysis
workplace.init()
with database.connect() as db:
 admin=workplace.add_employee(db,dict(email='qa@example.invalid',name='测试管理员',password='local-qa-only-482602'),True)
 specialist=workplace.add_employee(db,dict(email='staff@example.invalid',name='测试售后',password='local-qa-only-482602',role='aftersales'))
 other=workplace.add_employee(db,dict(email='other@example.invalid',name='其他项目售后',password='local-qa-only-482602',role='aftersales'))
 for u in (admin,specialist,other):u.update(csrf='qa',status='active')
 for n in (1,2):
  db.execute('INSERT INTO customers(id,code,name,contact,email,created_at) VALUES(?,?,?,?,?,?)',(f'c{n}',f'C{n}',f'客户{n}','联系人',f'c{n}@example.invalid',core.now()))
  db.execute('INSERT INTO projects(id,code,name,customer_id,created_at) VALUES(?,?,?,?,?)',(f'p{n}',f'P{n}',f'项目{n}',f'c{n}',core.now()))
 db.execute("INSERT INTO project_members(project_id,employee_id,assignment_role,assigned_at,assigned_by) VALUES(?,?,'member',CURRENT_TIMESTAMP,?)",('p1',specialist['id'],admin['id']))
 db.execute("INSERT INTO project_members(project_id,employee_id,assignment_role,assigned_at,assigned_by) VALUES(?,?,'member',CURRENT_TIMESTAMP,?)",('p2',other['id'],admin['id']))
def call(u,path,body=None):
 with database.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  code,h,b=aftercare.handle(db,u,'/api/aftercare/'+path,'GET' if body is None else 'POST',b'' if body is None else json.dumps(body).encode(),{'content-type':'application/json'},'http://127.0.0.1:8990')
  try:result=json.loads(b)
  except:result=b
  return code,result
record={'id':'QA-WORK-1','projectId':'p1','project':'项目1','customer':'客户1','product':'旋转设备H02','issue':'运行异响','problemType':'机械异响','reported':'2026-10-19','delivered':'2026-07-01','faultDate':'2026-10-18','owner':'测试售后','stage':'登记草稿','submitted':False,'attachments':[],'batchId':'QA-BATCH-1'}
code,result=call(specialist,'work-items',{'items':[record]});assert code==200,(code,result);assert result['versions'][0]['version']==1
code,result=call(specialist,'work-items');assert code==200,(code,result);assert len(result['items'])==1;record=result['items'][0]
assert call(other,'work-items')[1]['items']==[]
with database.connect() as db:assert not db.execute('SELECT 1 FROM service_tickets WHERE id=?',(record['id'],)).fetchone()
record.update(stage='审核',submitted=True)
code,result=call(specialist,'work-items',{'items':[record]});assert code==200,(code,result)
with database.connect() as db:
 r=core.need(db,'service_tickets',record['id']);assert r['project_id']=='p1';assert json.loads(r['payload'])['faultDate']=='2026-10-18'
 report=aftersales_analysis.report(db,specialist,{'p1':core.need(db,'projects','p1')},'2026-10-19');assert len(report['records'])==1;assert report['records'][0]['problem']=='机械异响'
code,result=call(specialist,'work-items',{'items':[record]});assert code==409,(code,result)
try:call(other,'work-items',{'items':[{**record,'cloudVersion':2}]});raise AssertionError('scope bypass')
except core.Problem as e:assert e.status==404
code,result=call(admin,'inbox');assert code==200,(code,result)
# Existing core client/project stable IDs must be honored in customer records and invites.
code,result=call(admin,'profiles',{'marketId':'c1','company':'客户1','contact':'联系人','email':'c1@example.invalid','phone':'','country':'中国','language':'zh','salesOwner':''});assert code==200,(code,result);cid=result['id']
code,result=call(admin,'stores',{'customerId':cid,'marketId':'p1','name':'项目1','orderNo':'P1','address':'地址','contact':'联系人','email':'c1@example.invalid','phone':''});assert code==200,(code,result)
code,result=call(admin,'invites',{'customerId':cid,'language':'zh'});assert code==200,(code,result);url=result['url'];assert '/aftercare/request?' in url
from urllib.parse import urlparse
code,result=call(None,'portal?'+urlparse(url).query);assert code==200,(code,result);assert len(result['stores'])==1;assert result['requests']==[]
print('PASS: durable internal drafts/import-shaped records, submit→shared statistics, stale version conflict, project isolation, customer profiles/stores/links and public portal.')
# Customer submits a real multipart request with an image; only the invite owner can read it.
from urllib.parse import parse_qs
import uuid
secret=parse_qs(urlparse(url).query)['token'][0]
store_id=result['stores'][0]['id']
payload={'submissionKey':str(uuid.uuid4()),'storeId':store_id,'contact':'客户联系人','email':'c1@example.invalid','phone':'123','address':'项目地址','language':'zh','issues':[{'product':'客户设备','issue':'设备振动','feedback':'运行时出现','delivered':'2026-07-01','evidence':''}]}
boundary='aftercare-'+uuid.uuid4().hex
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRTkAAAAASUVORK5CYII=')
raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'+json.dumps(payload,ensure_ascii=False)+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file_0"; filename="qa.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png+f'\r\n--{boundary}--\r\n'.encode()
with database.connect() as db:
 db.execute('BEGIN IMMEDIATE')
 code,h,b=aftercare.handle(db,None,'/api/aftercare/submit','POST',raw,{'content-type':'multipart/form-data; boundary='+boundary,'x-customer-token':secret,'cf-connecting-ip':'127.0.0.1'},'http://127.0.0.1:8990')
 response=json.loads(b);assert code==201,(code,response);rid=response['id']
code,result=call(None,'portal?token='+secret);assert code==200;assert result['requests'][0]['issues'][0]['files'];fid=result['requests'][0]['issues'][0]['files'][0]['id']
with database.connect() as db:
 code,h,b=aftercare.handle(db,None,'/api/aftercare/file/'+fid+'?token='+secret,'GET');assert code==200 and b==png
code,result=call(admin,'requests/'+rid+'/check',{'reviewerId':admin['id'],'confirmed':True});assert code==200,(code,result)
code,result=call(specialist,'work-items');customer_work=next(i for i in result['items'] if i.get('cloudRequestId')==rid)
# Source imported flow is preserved through customer confirmation and final closure.
customer_work.update(stage='客户验收',review={'approved':True,'method':'测试已处理','needOrder':'no'})
code,result=call(admin,'work-items',{'items':[customer_work]});assert code==200,(code,result)
customer_work['cloudVersion']=result['versions'][0]['version'];customer_work['stage']='负责人复核'
code,result=call(admin,'work-items',{'items':[customer_work]});assert code==200,(code,result)
customer_work['cloudVersion']=result['versions'][0]['version'];customer_work.update(stage='已关闭',actual='2026-10-19')
code,result=call(admin,'work-items',{'items':[customer_work]});assert code==200,(code,result)
code,result=call(None,'portal?token='+secret);assert result['requests'][0]['status']=='completed';assert result['requests'][0]['work'][0]['stage']=='已完成'
# A second customer's valid token still cannot read this customer's image.
code,result=call(admin,'profiles',{'marketId':'c2','company':'客户2','contact':'客户2','email':'c2@example.invalid','country':'中国','language':'zh'});cid2=result['id']
code,result=call(admin,'invites',{'customerId':cid2});secret2=parse_qs(urlparse(result['url']).query)['token'][0]
code,result=call(None,'file/'+fid+'?token='+secret2);assert code==403,(code,result)
print('PASS: customer multipart submission, durable attachment bytes, scoped file access, specialist handoff, acceptance→review→closure, and customer-visible completion.')

# Shared native cockpit edits refresh the workflow's optimistic version; workflow
# changes keep their precise stage and its six-stage cockpit projection aligned.
import aftersales_dashboard
with database.connect() as db:
 ticket=core.need(db,'service_tickets','QA-WORK-1')
 before_movements=db.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]
 aftersales_dashboard.save(db,admin,{'id':ticket['id'],'version':ticket['version'],'dashboard_stage':'工程下单'})
code,result=call(admin,'work-items');updated=next(d for d in result['items'] if d['id']=='QA-WORK-1');assert updated['stage']=='工程下单'
updated.update(stage='生产采购',engineering={'orderNumber':'QA-ENGINEERING-1','engineer':'测试管理员'})
code,result=call(admin,'work-items',{'items':[updated]});assert code==200,(code,result)
with database.connect() as db:
 ticket=core.need(db,'service_tickets','QA-WORK-1');assert aftersales_dashboard.phase(json.loads(ticket['payload']))=='生产采购'
 assert db.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]==before_movements
print('PASS: bidirectional legacy cockpit/workflow sync, precise workflow→six-stage dashboard projection and unchanged stock movements.')
# Original detailed internal pages persist independently of other group centers.
import aftercare_internal
from datetime import datetime
from zoneinfo import ZoneInfo
with database.connect() as db:
 before_stock=db.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]
 work=db.execute('SELECT * FROM af2_customer_work_items WHERE id=?',('QA-WORK-1',)).fetchone();d=json.loads(work['payload']);d['stage']='现场处理'
 db.execute('UPDATE af2_customer_work_items SET payload=?,version=version+1 WHERE id=?',(json.dumps(d,ensure_ascii=False),'QA-WORK-1'));aftercare.sync_ticket(db,'QA-WORK-1',admin['id'])
 request_id=work['request_id']
 # A real file uploaded through the protected internal route.
 boundary='internal-'+uuid.uuid4().hex
 raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="internal.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png+f'\r\n--{boundary}--\r\n'.encode()
 code,h,b=aftercare.handle(db,admin,'/api/aftercare/internal-files/QA-WORK-1','POST',raw,{'content-type':'multipart/form-data; boundary='+boundary},'http://127.0.0.1:8990')
 response=json.loads(b);assert code==200,(code,response);file=response['files'][0]
installation={'status':'待排期','items':[{'id':'i1','state':'待处理','note':''}],'photos':{},'signature':{'strokes':[]},'install':True}
body={'kind':'installation','id':'QA-WORK-1','ticketId':'QA-WORK-1','version':0,'value':installation}
code,result=call(admin,'internal-pages',body);assert code==200,(code,result)
try:call(admin,'internal-pages',body);raise AssertionError('internal stale write allowed')
except core.Problem as e:assert e.status==409
try:call(other,'internal-pages',{**body,'version':1});raise AssertionError('internal scope bypass')
except core.Problem as e:assert e.status==404
installation.update(status='售后结束',actual='2026-10-19',notes='完成检查',finished=True,presence='present',signer='客户',items=[{'id':'i1','state':'已完成','note':'检查无异常'}],photos={'i1':[file]},signature={'strokes':[[[.1,.1],[.4,.6]]]})
code,result=call(admin,'internal-pages',{**body,'version':1});assert code==200,(code,result)
code,result=call(admin,'internal-pages');stored=next(r for r in result['records'] if r['kind']=='installation');assert stored['value']['signature']==installation['signature'];assert stored['value']['photos']['i1'][0]['url']==file['url']
assert next(i for i in result['items'] if i['id']=='QA-WORK-1')['stage']=='客户验收'
cost={'cat':'物流','name':'回传运费','amount':12300,'paid':0,'payer':'公司','date':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),'review':'待核对','person':'测试售后','source':'QA-COST/1','voucherUrl':file['url'],'voucher':'internal.png'}
body={'kind':'finance','id':'QA-COST-1','ticketId':'QA-WORK-1','version':0,'value':cost}
code,result=call(specialist,'internal-pages',body);assert code==200,(code,result)
cost['review']='已核对'
try:call(specialist,'internal-pages',{**body,'version':1});raise AssertionError('specialist approved cost')
except core.Problem as e:assert e.status==403
code,result=call(admin,'internal-pages',{**body,'version':1});assert code==200,(code,result)
cost.update(paid=2300,paymentHistory=[{'amount':2300,'date':cost['date'],'reference':'QA-BANK-1'}])
code,result=call(admin,'internal-pages',{**body,'version':2});assert code==200,(code,result)
with database.connect() as db:
 assert db.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]==before_stock
 stored=json.loads(db.execute("SELECT payload FROM af2_department_records WHERE kind='finance' AND id='QA-COST-1'").fetchone()[0]);assert stored['paid']==2300 and stored['paymentHistory'][0]['reference']=='QA-BANK-1'
print('PASS: original internal installation photos/signatures and completion, finance vouchers/review/payment history, version conflict and project/role isolation; group stock unchanged.')
