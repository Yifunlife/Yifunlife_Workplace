import os,sys,tempfile,json,threading,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.environ.update(YIFUN_CONTAINER_MODE='0',YIFUN_PUBLIC_ORIGIN='',YIFUN_DATABASE_BACKEND='local',YIFUN_DEMO_MODE='0',YIFUN_DATA_ROOT=tempfile.mkdtemp(prefix='password-admin-qa-'))
sys.path.insert(0,str(root))
import workplace,database,core
workplace.init()
with database.connect() as db:
 admin=workplace.add_employee(db,dict(email='admin@example.invalid',name='管理员',password='admin-qa-password-123'),True)
 staff=workplace.add_employee(db,dict(email='staff@example.invalid',name='员工',password='employee-old-password-123',role='aftersales'))
server=workplace.ThreadingHTTPServer(('127.0.0.1',0),workplace.Handler);workplace.PORT=server.server_port
threading.Thread(target=server.serve_forever,daemon=True).start();origin='http://127.0.0.1:'+str(server.server_port)
def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(c,path,p=None,csrf=None):
 h={'Content-Type':'application/json','Origin':origin}
 if csrf:h['X-Yifun-Token']=csrf
 req=urllib.request.Request(origin+path,data=json.dumps(p).encode() if p is not None else None,headers=h)
 try:
  with c.open(req) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
a=client();s=client()
assert request(a,'/api/auth/login',{'email':admin['email'],'password':'admin-qa-password-123'})[0]==200
assert request(s,'/api/auth/login',{'email':staff['email'],'password':'employee-old-password-123'})[0]==200
at=request(a,'/api/auth/session')[1]['csrf'];st=request(s,'/api/auth/session')[1]['csrf']
body={'id':staff['id'],'password':'employee-new-password-456','confirm':'employee-new-password-456'}
assert request(s,'/api/employee-password',body,st)[0]==403
assert request(a,'/api/employee-password',body)[0]==403
assert request(a,'/api/employee-password',{**body,'confirm':'mismatch'},at)[0]==400
assert request(a,'/api/employee-password',{**body,'id':admin['id']},at)[0]==400
assert request(a,'/api/employee-password',body,at)[0]==200
assert request(s,'/api/auth/session')[1]['authenticated'] is False
assert request(a,'/api/auth/session')[1]['authenticated'] is True
assert request(client(),'/api/auth/login',{'email':staff['email'],'password':'employee-old-password-123'})[0] in (401,403)
assert request(client(),'/api/auth/login',{'email':staff['email'],'password':'employee-new-password-456'})[0]==200
with database.connect() as db:
 audit=db.execute("SELECT * FROM audit_events WHERE entity='employee' AND entity_id=?",(staff['id'],)).fetchall()
 assert audit and 'employee-new-password-456' not in str([dict(r) for r in audit])
 assert core.need(db,'employees',staff['id'])['role']=='aftersales'
os.environ.update(YIFUN_CONTAINER_MODE='1',YIFUN_AUTH_MODE='password',YIFUN_OWNER_EMAIL=admin['email'],YIFUN_VIEWER_EMAILS='viewer@example.invalid')
assert request(client(),'/api/auth/login',{'email':staff['email'],'password':'employee-new-password-456'})[0]==200
assert request(client(),'/api/auth/login',{'email':'unknown@example.invalid','password':'employee-new-password-456'})[0]==401
assert request(client(),'/api/auth/setup',{'email':'unknown@example.invalid','name':'未授权','password':'employee-new-password-456'})[0] in (401,403)
server.shutdown();server.server_close()
print('PASS: admin-only employee password reset, CSRF, confirmation, own-account protection, old-session revocation, old-password rejection, new login and secret-free audit.')
