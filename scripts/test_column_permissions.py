import os,sys,json,urllib.request,urllib.error,http.cookiejar,tempfile,threading,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
temporary=tempfile.mkdtemp(prefix='column-permissions-qa-')
os.environ.update(YIFUN_DATA_ROOT=temporary,YIFUN_DATABASE_BACKEND='local',YIFUN_CONTAINER_MODE='0',YIFUN_PUBLIC_ORIGIN='',YIFUN_DEMO_MODE='0')
sys.path.insert(0,str(root))
import database,workplace,column_permissions as cp,core
workplace.init()
server=workplace.ThreadingHTTPServer(('127.0.0.1',0),workplace.Handler);workplace.PORT=server.server_port
threading.Thread(target=server.serve_forever,daemon=True).start()
with database.connect() as db:
 admin=workplace.add_employee(db,{'email':'admin@example.invalid','name':'权限测试管理员','password':'admin-only-test-123456'},True)
 target=db.execute("SELECT * FROM employees WHERE email='permission-qa@example.invalid'").fetchone()
 if not target:target=workplace.add_employee(db,{'email':'permission-qa@example.invalid','name':'权限验证员工','role':'purchasing','password':'permissions-only-123456'})
 target=dict(target)
 data=cp.config(db);cp.save(db,admin,{'kind':'employees','subject':target['id'],'version':data['version'],'grants':{'center-procurement':0,'procurement':1,'expenses':0,'center-aftersales-workflow':0,'center-aftersales-issues':0,'orders':0,'inventory':0,'home':0,'customers':0,'masters':0}})
 for kind,subject in [('roles','admin'),('employees',admin['id'])]:
  try:cp.save(db,admin,{'kind':kind,'subject':subject,'version':cp.config(db)['version'],'grants':{}});raise AssertionError('admin lock bypass')
  except core.Problem as e:assert e.status in (400,403)
 try:cp.save(db,admin,{'kind':'employees','subject':target['id'],'version':-1,'grants':{}});raise AssertionError('stale allowed')
 except core.Problem as e:assert e.status==409
 assert cp.level(db,target,'center-procurement')==0
 assert cp.level(db,target,'procurement')==1
 # Existing role scope continues to deny unrelated finance actions even with level 2.
 assert cp.level(db,target,'finance')==2
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar));origin='http://127.0.0.1:'+str(server.server_port)
def req(path,p=None,csrf=None,bridge=False):
 headers={'Content-Type':'application/json','Origin':origin}
 if csrf:headers['X-Yifun-Token']=csrf
 if bridge:headers['X-Workspace-Bridge']=workplace.BRIDGE_PATH.read_text()
 try:
  with client.open(urllib.request.Request(origin+path,data=json.dumps(p).encode() if p is not None else None,headers=headers),timeout=20) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
assert req('/api/auth/login',{'email':target['email'],'password':'permissions-only-123456'})[0]==200
code,session=req('/api/auth/session');csrf=session['csrf'];assert session['column_levels']['procurement']==1
for path in ['/api/centers/dashboard?center=procurement','/api/ops/view?page=expenses','/api/service-state','/api/aftercare/work-items','/api/column-permissions','/api/centers/dashboard?center=aftersales&column=center-aftersales-issues']:
 assert req(path)[0]==403,path
# Both native module operations and direct legacy write API enforce the same read-only key.
assert req('/api/internal/session?module=procurement&method=GET',bridge=True)[0]==200
assert req('/api/internal/session?module=procurement&method=POST',bridge=True)[0]==403
assert req('/api/column-permissions',{'kind':'roles','subject':'purchasing','version':0,'grants':{}},csrf)[0]==403
assert req('/api/action/create-po',{},csrf)[0]==403
assert req('/api/ops/action/save',{'page':'expenses'},csrf)[0]==403
code,state=req('/api/view/overview');assert code==200
for field in ['baselines','changes','deliveries','stock_history','service_requests','reservations','products']:assert state[field]==[],field
assert all(set(row)<=set(['id','code','name','customer_id','customer_name']) for row in state['projects'])
with database.connect() as db:
 data=cp.config(db);cp.save(db,admin,{'kind':'roles','subject':'purchasing','version':data['version'],'grants':{'procurement':0}})
 assert cp.level(db,target,'procurement')==1,'individual override must win'
assert req('/api/view/overview')[0]==401,'permission edits must revoke old sessions'
server.shutdown();server.server_close();shutil.rmtree(temporary)
print('PASS: role defaults, personal override precedence, direct GET/POST denial, overview redaction, no privilege escalation, admin lock, stale conflict and session invalidation')
