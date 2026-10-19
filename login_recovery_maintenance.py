"""One-time owner-requested login recovery; no password or session is changed here.

Only a SHA-256 reset-token digest ships with the source. The raw link stays with
the requesting owner and uses the existing expiring, single-use reset endpoint.
The persistent marker prevents restoring a consumed link on later restarts.
"""
import os
import time
import core
import runtime_config

TARGET = 'markfang458@hotmail.com'
DIGEST = 'a12fa11988881f5f31f42517921cc5899abd1dddcfe83fc675e1202350afbc07'
EXPIRES = 1792371815
MARKER = 'owner_login_recovery_20261019_v1'


def issue(db):
    if (not runtime_config.container_mode() or os.environ.get('YIFUN_DEMO_MODE')!='1'
            or runtime_config.owner_email()!=TARGET or time.time()>=EXPIRES):
        return False
    if db.execute('SELECT 1 FROM settings WHERE key=?',(MARKER,)).fetchone():
        return False
    user=core.row(db,"SELECT * FROM employees WHERE email=? AND role IN ('admin','ceo') AND status='active'",(TARGET,))
    if not user: return False
    db.execute('DELETE FROM account_recovery_links WHERE email=? OR expires<?',(TARGET,time.time()))
    db.execute('INSERT INTO account_recovery_links(token_hash,email,expires,created_by) VALUES(?,?,?,?)',(DIGEST,TARGET,EXPIRES,user['id']))
    db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(MARKER,core.now()))
    core.audit(db,user,'employee',user['id'],'管理员请求一次性账号恢复',{'expires':EXPIRES,'source':'authorized-owner-maintenance'})
    return True
