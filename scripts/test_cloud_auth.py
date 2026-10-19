"""Test cloud account setup and read-only rules against an isolated HTTP server."""
import http.client
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(YIFUN_DATA_ROOT=directory, YIFUN_CONTAINER_MODE='1',
            YIFUN_PUBLIC_ORIGIN='https://workplace.example.invalid', YIFUN_OWNER_EMAIL='owner@example.invalid',
            YIFUN_VIEWER_EMAILS='viewer@example.invalid', YIFUN_DEMO_MODE='1', YIFUN_DATABASE_BACKEND='local')
        import workplace, database
        workplace.init()
        server = workplace.ThreadingHTTPServer(('127.0.0.1', 0), workplace.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def call(path, email='owner@example.invalid', body=None, cookie=None, csrf=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            headers = {'Host':'workplace.example.invalid', 'Origin':'https://workplace.example.invalid',
                'X-Yifun-Verified-Email':email, 'Content-Type':'application/json'}
            if email is None: headers.pop('X-Yifun-Verified-Email', None)
            if cookie: headers['Cookie'] = cookie
            if csrf: headers['X-Yifun-Token'] = csrf
            connection.request('GET' if body is None else 'POST', path,
                None if body is None else json.dumps(body), headers)
            response = connection.getresponse()
            result = (response.status, dict(response.getheaders()), json.loads(response.read()))
            connection.close()
            return result

        try:
            assert call('/api/auth/session', 'viewer@example.invalid')[0] == 409
            assert call('/api/auth/setup', body={'email':'unlisted@example.invalid',
                'name':'Test', 'password':secrets.token_urlsafe(24)})[0] == 403
            owner = {'email':'owner@example.invalid', 'name':'模拟管理员', 'password':secrets.token_urlsafe(24)}
            status, headers, result = call('/api/auth/setup', body=owner)
            assert status == 200 and result['user']['role'] == 'admin'
            assert '; Secure' in headers['Set-Cookie']
            owner_cookie = headers['Set-Cookie'].split(';')[0]
            assert call('/api/auth/session', cookie=owner_cookie)[2]['authenticated']
            viewer = {'email':'viewer@example.invalid', 'name':'模拟查看者', 'password':secrets.token_urlsafe(24)}
            status, headers, result = call('/api/auth/setup', 'viewer@example.invalid', viewer)
            assert status == 200 and result['user']['role'] == 'ceo'
            cookie = headers['Set-Cookie'].split(';')[0]
            session = call('/api/auth/session', 'viewer@example.invalid', cookie=cookie)[2]
            assert session['read_only'] and session['authenticated']
            assert not call('/api/auth/session', 'owner@example.invalid', cookie=cookie)[2]['authenticated']
            assert call('/api/action/customers', 'viewer@example.invalid', {}, cookie, session['csrf'])[0] == 403
            status, _, overview = call('/api/view/overview', 'viewer@example.invalid', cookie=cookie)
            assert status == 200 and len(overview['customers']) == 3
            assert call('/api/context', 'viewer@example.invalid', {'project_id':'DEMO-PROJECT-1'}, cookie, session['csrf'])[0] == 200
            with database.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0] == 3
                assert not list(db.execute('PRAGMA foreign_key_check'))
            os.environ['YIFUN_AUTH_MODE']='password'
            anonymous=call('/api/auth/session',None)
            assert anonymous[0]==200 and not anonymous[2]['authenticated'] and not anonymous[2]['needsSetup']
            assert call('/api/auth/setup',None,owner)[0]==403
            assert call('/api/auth/login',None,{**owner,'password':secrets.token_urlsafe(24)})[0]==401
            assert call('/api/auth/login',None,{**owner,'email':'unlisted@example.invalid'})[0]==401
            status, native_headers, native_result=call('/api/auth/login',None,owner)
            assert status==200 and native_result['user']['role']=='admin'
            native_cookie=native_headers['Set-Cookie'].split(';')[0]
            assert call('/api/view/overview',None,cookie=native_cookie)[0]==200
            status, native_headers, native_result=call('/api/auth/login',None,viewer)
            assert status==200
            native_cookie=native_headers['Set-Cookie'].split(';')[0]
            native_session=call('/api/auth/session',None,cookie=native_cookie)[2]
            assert native_session['read_only']
            assert call('/api/action/customers',None,{},native_cookie,native_session['csrf'])[0]==403
            assert call('/api/view/overview',None,cookie=native_cookie)[0]==200
            assert call('/api/auth/recover',None,{'password':secrets.token_urlsafe(24),'confirm':'mismatch'})[0]==403
            replacement=secrets.token_urlsafe(24)
            assert call('/api/auth/recover','owner@example.invalid',{'password':replacement,'confirm':replacement})[0]==200
            assert call('/api/auth/login',None,owner)[0]==401
            assert call('/api/auth/login',None,{**owner,'password':replacement})[0]==200
            owner_current=replacement
            assert call('/api/view/overview',None,cookie=native_cookie)[0]==200
            with database.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==3
                assert db.execute('SELECT COUNT(*) FROM employees WHERE email=?',('owner@example.invalid',)).fetchone()[0]==1
            os.environ['YIFUN_VIEWER_EMAILS']='viewer@example.invalid,new-viewer@example.invalid'
            replacement=secrets.token_urlsafe(24)
            restored=call('/api/auth/recover','new-viewer@example.invalid',{'name':'模拟新增查看者','password':replacement,'confirm':replacement,'role':'admin'})
            assert restored[0]==200
            signed=call('/api/auth/login',None,{'email':'new-viewer@example.invalid','password':replacement})
            assert signed[0]==200 and signed[2]['user']['role']=='ceo'
            cookie=signed[1]['Set-Cookie'].split(';')[0]
            assert call('/api/auth/session',None,cookie=cookie)[2]['read_only']
            request=call('/api/auth/recovery-request',None,{'email':'viewer@example.invalid'})
            assert request[0]==200
            assert call('/api/auth/recovery-request',None,{'email':'stranger@example.invalid'})[2]==request[2]
            assert call('/api/employee-recovery-link',None,{'email':'viewer@example.invalid'},cookie,signed[2]['csrf'])[0]==403
            owner_login=call('/api/auth/login',None,{**owner,'password':owner_current})
            owner_cookie=owner_login[1]['Set-Cookie'].split(';')[0]
            owner_csrf=owner_login[2]['csrf']
            requests=call('/api/recovery-requests',None,cookie=owner_cookie)
            assert requests[0]==200 and any(item['email']=='viewer@example.invalid' for item in requests[2]['items'])
            generated=call('/api/employee-recovery-link',None,{'email':'viewer@example.invalid'},owner_cookie,owner_csrf)
            assert generated[0]==200
            token=generated[2]['url'].split('#token=')[1]
            fresh_password=secrets.token_urlsafe(24)
            reset={'token':token,'password':fresh_password,'confirm':fresh_password,'email':'owner@example.invalid','role':'admin'}
            assert call('/api/auth/reset-link',None,reset)[0]==200
            assert call('/api/auth/reset-link',None,reset)[0]==403
            viewer_login=call('/api/auth/login',None,{**viewer,'password':fresh_password})
            assert viewer_login[0]==200 and viewer_login[2]['user']['role']=='ceo'
            assert call('/api/auth/login',None,{**owner,'password':owner_current})[0]==200
            assert not call('/api/auth/session',None,cookie=native_cookie)[2]['authenticated']
            generated=call('/api/employee-recovery-link',None,{'email':'viewer@example.invalid'},owner_cookie,owner_csrf)
            expired=generated[2]['url'].split('#token=')[1]
            with database.connect() as db:db.execute('UPDATE account_recovery_links SET expires=0')
            assert call('/api/auth/reset-link',None,{**reset,'token':expired})[0]==403
            print('PASS: self-selected account setup, verified identity, Secure cookies, read-only rules and simulated view/context access and direct password login')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()

if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable,str(Path(__file__).resolve().with_name("test_aftercare_integration.py"))],check=True)
