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
 import android_ops as ops,time,hashlib,hmac
 def resource(kind,**p):
  r=admin('resource',{'kind':kind,**p});assert r[0]==200,r;return r[2]
 def snapshot():return call('/api/software',cookie=cookie)[2]
 d=overview['devices'][0]['id']
 site=resource('site',customer_id=customer,name='真实场地',address='测试路',contact='测试人员')['id']
 assert site in [r['id'] for r in snapshot()['resources']]
 feature=resource('feature',product_id=product,name='赛事模式',key='tournament')['id']
 entitlement=resource('entitlement',device_id=d,resource_id=feature,expires_at=time.time()+86400)['id']
 assert admin('resource',{'kind':'entitlement','device_id':d,'resource_id':feature})[0]==409
 assert admin('resource',{'kind':'feature','product_id':product,'name':'重复','key':'tournament'})[0]==409
 artifact={'name':'飞镖1.2','product_id':product,'url':'https://downloads.example.com/game.apk','sha256':'a'*64,'certificate_sha256':'b'*64,'version':'1.2','version_code':2,'min_sdk':26,'size_bytes':1024}
 pkg=resource('package',**artifact)['id']
 assert admin('resource',{'kind':'package',**artifact})[0]==409
 assert admin('resource',{'kind':'content','name':'x','product_id':product,'version':'1','url':'http://localhost/a','sha256':'a'*64,'size_bytes':1})[0]==400
 content=resource('content',name='付费皮肤',product_id=product,url='https://downloads.example.com/content.zip',sha256='c'*64,size_bytes=200,version='1',pricing='paid')['id']
 assert admin('task',{'device_id':d,'task_type':'sync_content','resource_id':content})[0]==400
 grant=resource('content_grant',device_id=d,resource_id=content)['id']
 blocked=admin('task',{'device_id':d,'task_type':'install_apk','resource_id':pkg});assert blocked[0]==200 and blocked[2]['state']=='waiting_adapter'
 assert admin('task-action',{'id':blocked[2]['id'],'operation':'queue'})[0]==400
 hook=resource('webhook',name='测试回调',url='https://partner.example.com/hook',events=['task.succeeded','task.failed','device.offline','device.recovered','game.session_ended'],state='active',customer_id=customer)
 hook_id=hook['id'];signing=hook['signing_secret'];assert signing not in json.dumps(snapshot())
 telemetry={**hb['telemetry'],'protocol_version':2,'supported_tasks':['sync_config','collect_agent_logs']}
 def sync(request='sync-request-0001',events=None,receipt=None,token=secret):
  p={'request_id':request,'telemetry':telemetry,'events':events or []}
  if receipt:p['receipt']=receipt
  return call('/api/software/agent/sync',p,token=token)
 initial=sync();assert initial[0]==200,initial
 config=initial[2]['config'];assert config['features'][0]['key']=='tournament' and config['contents'][0]['id']==content
 t=admin('task',{'device_id':d,'task_type':'sync_config'});assert t[0]==200 and t[2]['state']=='draft';task=t[2]['id']
 assert admin('task-action',{'id':task,'operation':'queue'})[0]==200
 first=sync();assert first[0]==200 and first[2]['task']['id']==task,first
 lease=first[2]['task']['lease'];assert lease not in json.dumps(snapshot())
 repeat=sync();assert repeat[2]['task']['lease']==lease
 assert sync('different-request-id')[2]['task'] is None
 assert admin('task-action',{'id':task,'operation':'cancel'})[0]==400
 receipt={'task_id':task,'lease':lease,'state':'succeeded','result':{'revision':config['revision']}}
 ev={'event_id':'event-1','category':'diagnostic','data':{'message':'hello','task_id':task}}
 complete=sync('sync-request-0002',[ev],receipt);assert complete[0]==200,complete
 assert complete[2]['acknowledged_events']==['event-1'] and complete[2]['acknowledged_task']==task
 replay=sync('sync-request-0002',[ev],receipt);assert replay[0]==200
 assert len([e for e in snapshot()['events'] if e['event_id']=='event-1'])==1
 assert len(snapshot()['deliveries'])==1
 assert sync('sync-request-0003',[{**ev,'data':{'message':'changed'}}])[0]==409
 assert sync('sync-request-0003',[{'event_id':'bad','category':'diagnostic','data':{'device_secret':'no'}}])[0]==400
 other=call('/api/software/agent/bind',{'code':code,'installation_id':'other','device_secret':secrets.token_urlsafe(32)});assert other[0]==403
 license2=admin('license',{'product_id':product,'customer_id':customer,'site_id':site,'label':'板2'});assert license2[0]==200
 secret2=secrets.token_urlsafe(32)
 other=call('/api/software/agent/bind',{'code':license2[2]['code'],'installation_id':'other','device_secret':secret2});assert other[0]==200,other
 assert sync('sync-request-0004',receipt=receipt,token=secret2)[0]==403
 game={'event_id':'game-1','category':'game','data':{'event':'game.session_ended','session_id':'session-1'}}
 assert sync('sync-request-0005',[game])[0]==200
 assert len(snapshot()['deliveries'])==2
 offline=resource('alert_rule',name='长时间未连接',rule_type='offline',threshold=30)['id']
 with database.connect() as db:
  db.execute('UPDATE android_devices SET last_seen=? WHERE id=?',(time.time()-4000,d));ops.maintenance(db);ops.maintenance(db)
 assert len([a for a in snapshot()['alerts'] if a['state']=='open' and a['device_id']==d])==1
 assert sync('sync-request-0006')[0]==200
 with database.connect() as db:ops.maintenance(db)
 assert all(a['state']=='resolved' for a in snapshot()['alerts'] if a['device_id']==d)
 retry_task=admin('task',{'device_id':d,'task_type':'sync_config'})[2]['id'];assert admin('task-action',{'id':retry_task,'operation':'queue'})[0]==200
 claimed=sync('sync-request-0010')[2]['task'];assert claimed['id']==retry_task
 with database.connect() as db:db.execute('UPDATE android_tasks SET lease_until=0 WHERE id=?',(retry_task,));ops.maintenance(db)
 stale={'task_id':retry_task,'lease':claimed['lease'],'state':'succeeded','result':{'value':'stale'}}
 stale_result=sync('sync-request-0011',receipt=stale);assert stale_result[0]==200 and stale_result[2]['receipt_status']=='stale_lease',stale_result
 newtask=stale_result[2]['task'];assert newtask['id']==retry_task and newtask['lease']!=claimed['lease']
 with database.connect() as db:db.execute("UPDATE android_tasks SET attempts=3,lease_until=0 WHERE id=?",(retry_task,));ops.maintenance(db)
 assert next(t for t in snapshot()['tasks'] if t['id']==retry_task)['state']=='failed'
 assert admin('task-action',{'id':retry_task,'operation':'retry'})[0]==400
 r=next(r for r in snapshot()['resources'] if r['id']==entitlement)
 assert admin('resource-state',{'id':entitlement,'revision':r['revision']+1,'state':'disabled'})[0]==409
 assert admin('resource-state',{'id':entitlement,'revision':r['revision'],'state':'disabled'})[0]==200
 assert sync('sync-request-0012')[2]['config']['features']==[]
 original_resolver=ops.socket.getaddrinfo
 ops.socket.getaddrinfo=lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))]
 try:
  try:ops.send_delivery({'url':'https://partner.example.com/hook','secret':signing},'{}','delivery-test');raise AssertionError('SSRF allowed')
  except ValueError:pass
 finally:ops.socket.getaddrinfo=original_resolver
 class Response:
  status=204
  def read(self,n):return b''
 class Transport:
  captured=None
  def __init__(self,*a):pass
  def request(self,method,path,body,headers):Transport.captured=(method,path,body,headers)
  def getresponse(self):return Response()
  def close(self):pass
 original_conn=ops.PinnedHTTPS
 ops.PinnedHTTPS=Transport;ops.socket.getaddrinfo=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))]
 try:
  assert ops.send_delivery({'url':'https://partner.example.com/hook','secret':signing},'{}','delivery-test')=='HTTP 204'
  h=Transport.captured[3];expected=hmac.new(signing.encode(),h['X-Yifun-Timestamp'].encode()+b'.{}',hashlib.sha256).hexdigest();assert h['X-Yifun-Signature']=='sha256='+expected
 finally:ops.PinnedHTTPS=original_conn;ops.socket.getaddrinfo=original_resolver
 print('PASS: resources, ownership, artifacts, grants, adapter gating, task lifecycle, deterministic lease replay, stale receipts, retry ceiling, event idempotency, alert recovery, webhook outbox, HMAC signing and SSRF rejection')
 key=overview['enrollments'][0]['id'];assert admin('revoke',{'kind':'enrollment','id':key})[0]==200
 assert call('/api/software/agent/heartbeat',hb,token=secret)[0]==401
 assert call('/api/software/agent/bind',body)[0]==403
 with database.connect() as db:
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert db.execute('SELECT token_hash FROM android_devices').fetchone()[0]!=secret
 server.shutdown();print('PASS: HTTP authentication, CSRF, product validation, one-time enrollment, idempotent retry, telemetry, credential isolation, revocation, persistent data and foreign keys')
