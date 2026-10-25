import os,sys,tempfile,threading,json,http.client,secrets,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(YIFUN_DATA_ROOT=tmp,YIFUN_DATABASE_BACKEND='local',YIFUN_CONTAINER_MODE='1',YIFUN_PUBLIC_ORIGIN='https://workplace.example.invalid',YIFUN_OWNER_EMAIL='owner@example.invalid',YIFUN_VIEWER_EMAILS='viewer@example.invalid',YIFUN_DEMO_MODE='1')
 import workplace,database,software_work as work,core
 workplace.init();server=workplace.ThreadingHTTPServer(('127.0.0.1',0),workplace.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 def call(path,body=None,cookie=None,csrf=None):
  headers={'Host':'workplace.example.invalid','Origin':'https://workplace.example.invalid','X-Yifun-Verified-Email':'owner@example.invalid','Content-Type':'application/json'}
  if cookie:headers['Cookie']=cookie
  if csrf:headers['X-Yifun-Token']=csrf
  con=http.client.HTTPConnection('127.0.0.1',server.server_port);con.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers);r=con.getresponse();out=(r.status,dict(r.getheaders()),json.loads(r.read()));con.close();return out
 r=call('/api/auth/setup',{'email':'owner@example.invalid','name':'测试管理员','password':secrets.token_urlsafe(24)});assert r[0]==200,r
 cookie=r[1]['Set-Cookie'].split(';')[0];csrf=r[2]['csrf']
 def get():return call('/api/software/work',cookie=cookie)[2]
 def post(p):return call('/api/software/work',p,cookie,csrf)
 assert call('/api/software/work')[0]==401
 assert call('/api/software/work',{'action':'create'},cookie)[0]==403
 with database.connect() as db:
  owner=dict(db.execute("SELECT * FROM employees WHERE email='owner@example.invalid'").fetchone());engineer={**owner,'id':core.uid(),'email':'engineer@example.invalid','name':'测试软件工程师','role':'engineering'}
  db.execute('INSERT INTO employees('+','.join(engineer)+') VALUES('+','.join('?' for _ in engineer)+')',tuple(engineer.values()));db.execute("INSERT INTO center_members VALUES(?,'software')",(engineer['id'],))
 payload={'action':'create','title':'传送带互动研发','brief':'产品研发中心要求与验收标准','request_id':'test-request-001'}
 r=post(payload);assert r[0]==200,r;key=r[2]['id'];assert post(payload)[2]['id']==key and len(get()['items'])==1
 assert post({**payload,'title':'变更内容'})[0]==409
 def current(key=key):return next(t for t in get()['items'] if t['id']==key)
 def action(name,**p):return post({'action':name,'id':key,'version':current()['version'],**p})
 assert current()['source_center']=='product_rd'
 assert action('start')[0]==403
 assert action('assign',owner_id=engineer['id'],due_date='2026-12-01')[0]==200
 assert action('start')[0]==200
 with database.connect() as db:db.execute('UPDATE software_work_sessions SET started_at=started_at-120 WHERE task_id=?',(key,))
 assert current()['elapsed_seconds']>=120
 r=post({**payload,'request_id':'test-request-002','title':'第二个任务'});key2=r[2]['id'];t2=next(t for t in get()['items'] if t['id']==key2)
 assert post({'action':'assign','id':key2,'version':t2['version'],'owner_id':engineer['id']})[0]==200
 t2=next(t for t in get()['items'] if t['id']==key2);assert post({'action':'start','id':key2,'version':t2['version']})[0]==409
 assert action('pause',note='等待研发补充素材')[0]==200
 first=current()['elapsed_seconds'];second=current()['elapsed_seconds'];assert first==second
 assert action('start')[0]==200
 assert action('submit',result_reference='共享目录/测试版本.apk')[0]==200
 assert current()['state']=='review'
 assert action('return',note='补充一个交互效果')[0]==200
 assert action('start')[0]==200
 assert action('submit',result_reference='共享目录/测试版本2.apk')[0]==200
 assert action('accept')[0]==200 and current()['state']=='completed'
 assert len(current()['history'])>=9
 with database.connect() as db:
  assert not db.execute('SELECT 1 FROM software_work_sessions WHERE task_id=? AND ended_at IS NULL',(key,)).fetchone()
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  # R&D members and software members resolve the same persisted task IDs without duplicate tables.
  old=work.runtime_config.read_only;work.runtime_config.read_only=lambda u:False
  rd={**engineer,'id':core.uid(),'email':'rd@example.invalid','name':'测试研发人员'}
  db.execute('INSERT INTO employees('+','.join(rd)+') VALUES('+','.join('?' for _ in rd)+')',tuple(rd.values()));db.execute("INSERT INTO center_members VALUES(?,'product_rd')",(rd['id'],))
  item=work.execute(db,rd,{'action':'create','title':'研发提报','brief':'明确的研发验收要求','request_id':'rd-request-001'})
  assert item['id'] in {t['id'] for t in work.overview(db,owner)['items']}
  assert item['id'] in {t['id'] for t in work.overview(db,rd)['items']}
  try:work.execute(db,engineer,{'action':'create','title':'x','brief':'x','request_id':'sw-request-001'});raise AssertionError('Software center created R&D source')
  except core.Problem as e:assert e.status==403
  work.runtime_config.read_only=old
 server.shutdown();print('PASS: shared product-R&D source, assignment, single running task, pause exclusion, accumulated timing, review/rework/acceptance, optimistic locking, idempotent intake and existing permissions')
