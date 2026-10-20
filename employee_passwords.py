"""Administrator password resets for existing employee identities only."""
import secrets,hmac
import core,runtime_config

def reset(db,actor,p):
    import workplace
    core.permit(actor,'admin')
    if runtime_config.read_only(actor):raise core.Problem('当前账号仅可查看',403)
    target=core.need(db,'employees',p.get('id'))
    if target['id']==actor['id']:raise core.Problem('请在个人账号中修改自己的密码')
    secret=workplace.password(p.get('password'))
    if not isinstance(p.get('confirm'),str) or not hmac.compare_digest(secret,p['confirm']):raise core.Problem('两次输入的新密码不一致')
    salt=secrets.token_hex(16)
    db.execute('UPDATE employees SET password_hash=?,salt=? WHERE id=?',(workplace.password_hash(secret,salt),salt,target['id']))
    db.execute('DELETE FROM employee_sessions WHERE user_id=?',(target['id'],))
    for table in ('account_recovery_links','account_recovery_requests','login_attempts'):
        db.execute('DELETE FROM '+table+' WHERE email=?',(target['email'],))
    core.audit(db,actor,'employee',target['id'],'管理员重置员工密码',{'email':target['email'],'sessions_revoked':True})
    return {'ok':True,'id':target['id'],'disabled':target['status']!='active'}
