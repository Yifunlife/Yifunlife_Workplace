import os,sys,tempfile,threading,json,http.client,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(YIFUN_DATA_ROOT=tmp,YIFUN_DATABASE_BACKEND='local',YIFUN_CONTAINER_MODE='1',YIFUN_PUBLIC_ORIGIN='https://workplace.example.invalid',YIFUN_OWNER_EMAIL='owner@example.invalid',YIFUN_VIEWER_EMAILS='viewer@example.invalid',YIFUN_DEMO_MODE='1')
 import workplace,database
 workplace.init();server=workplace.ThreadingHTTPServer(('127.0.0.1',0),workplace.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 def call(path,body=None,cookie=None,csrf=None,token=None,email='owner@example.invalid'):
  h={'Host':'workplace.example.invalid','Origin':'https://workplace.example.invalid','Content-Type':'application/json','X-Yifun-Verified-Email':email}
  if cookie:h['Cookie']=cookie
  if csrf:h['X-Yifun-Token']=csrf
  if token:h['Authorization']='Bearer '+token
  conn=http.client.HTTPConnection('127.0.0.1',server.server_port);conn.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),h);r=conn.getresponse();result=(r.status,dict(r.getheaders()),json.loads(r.read()));conn.close();return result
 r=call('/api/auth/setup',{'email':'owner@example.invalid','name':'测试管理员','password':secrets.token_urlsafe(24)});assert r[0]==200,r
 cookie=r[1]['Set-Cookie'].split(';')[0];csrf=r[2]['csrf']
 def admin(action,p):return call('/api/software/action/'+action,p,cookie,csrf)
 assert call('/api/software')[0]==401
 info=call('/api/software',cookie=cookie);assert info[0]==200 and info[2]['devices']==[],info
 assert call('/api/software/action/product',{'name':'x','package_name':'com.test.app'},cookie)[0]==403
 assert admin('product',{'name':'互动飞镖','package_name':'not-a-package'})[0]==400
 assert admin('product',{'name':'互动飞镖','package_name':'com.test.dart'})[0]==200
 assert admin('product',{'name':'重复','package_name':'com.test.dart'})[0]==409
 data=call('/api/software',cookie=cookie)[2];assert data['customers'];product=data['products'][0]['id'];customer=data['customers'][0]['id']
 r=admin('license',{'product_id':product,'customer_id':customer,'site':'测试店','label':'测试安卓板'});assert r[0]==200,r
 code=r[2]['code'];secret=secrets.token_urlsafe(32)
 body={'code':code,'installation_id':'unit-install-1','device_secret':secret,'telemetry':{'android_version':'12','sdk_int':31,'model':'Test','device_owner':False}}
 assert call('/api/software/agent/bind',{**body,'code':'INVALID'})[0]==403
 r=call('/api/software/agent/bind',body);assert r[0]==200,r
 assert r[2]['package_name']=='com.test.dart'
 assert call('/api/software/agent/bind',body)[2]['device_id']==r[2]['device_id']
 assert call('/api/software/agent/bind',{**body,'installation_id':'different','device_secret':secrets.token_urlsafe(32)})[0]==403
 hb={'telemetry':{'package_name':'com.test.dart','app_version':'1.0','app_version_code':1,'android_version':'12','device_owner':False,'managed_install':False,'reboot':False}}
 assert call('/api/software/agent/heartbeat',hb,token='wrong')[0]==401
 assert call('/api/software/agent/heartbeat',{'telemetry':{'package_name':'com.wrong'}},token=secret)[0]==400
 assert call('/api/software/agent/heartbeat',hb,token=secret)[0]==200
 overview=call('/api/software',cookie=cookie)[2];assert len(overview['devices'])==1 and overview['devices'][0]['connection']=='online'
 assert secret not in json.dumps(overview) and code not in json.dumps(overview)
 key=overview['enrollments'][0]['id'];assert admin('revoke',{'kind':'enrollment','id':key})[0]==200
 assert call('/api/software/agent/heartbeat',hb,token=secret)[0]==401
 assert call('/api/software/agent/bind',body)[0]==403
 with database.connect() as db:
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert db.execute('SELECT token_hash FROM android_devices').fetchone()[0]!=secret
 server.shutdown();print('PASS: HTTP authentication, CSRF, product validation, one-time enrollment, idempotent retry, telemetry, credential isolation, revocation, persistent data and foreign keys')
