"""Unique login names mapped to existing employee identities; no password changes."""
import unicodedata
import sqlite3
import core

def normalize(value):
    if not isinstance(value,str):raise core.Problem('请填写工号')
    value=unicodedata.normalize('NFKC',value).strip().casefold()
    if not 1<=len(value)<=40 or not all(ch.isalnum() or ch in '._-' for ch in value):
        raise core.Problem('工号为 1 至 40 位，可使用中文、字母、数字及 . _ -')
    return value

def register(db,user,requested=None):
    if not requested or not str(requested).strip():return None
    username=normalize(requested)
    try:db.execute('INSERT INTO employee_login_names(employee_id,username) VALUES(?,?)',(user['id'],username))
    except sqlite3.IntegrityError:raise core.Problem('工号已被使用，请换一个',409)
    return username

def find(db,identifier):
    identifier=core.text(identifier,'工号',limit=254).strip()
    # Existing saved email logins remain usable during the transition.
    if '@' in identifier:
        return core.row(db,'SELECT e.*,n.username FROM employees e LEFT JOIN employee_login_names n ON n.employee_id=e.id WHERE e.email=?',(identifier.lower(),))
    username=normalize(identifier)
    return core.row(db,'SELECT e.*,n.username FROM employee_login_names n JOIN employees e ON e.id=n.employee_id WHERE n.username=?',(username,))

def rename(db,actor,employee_id,value):
    core.permit(actor,'admin');employee=core.need(db,'employees',employee_id)
    username=normalize(value)
    existing=core.row(db,'SELECT username FROM employee_login_names WHERE employee_id=?',(employee_id,))
    if existing and existing['username']==username:return {'ok':True,'username':username}
    try:
        db.execute('INSERT INTO employee_login_names(employee_id,username) VALUES(?,?) ON CONFLICT(employee_id) DO UPDATE SET username=excluded.username',(employee_id,username))
    except sqlite3.IntegrityError:raise core.Problem('工号已被使用，请换一个',409)
    core.audit(db,actor,'employee',employee['id'],'修改登录工号',{'before':existing['username'] if existing else None,'after':username})
    return {'ok':True,'username':username}
