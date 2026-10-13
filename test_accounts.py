"""One-time, explicitly authorized cloud demonstration account credentials."""
import os
import runtime_config
MARKER = 'authorized_test_passwords_20261012_v1'
CREDENTIALS = [('markfang458@hotmail.com', '48b18c0ff92a928e67778de481f4c959', 'f781838fc9176ace675e4764b9b24a5c6be2dd42c9adbd886b83afe7a7c25338'), ('yifunlife@hotmail.com', 'ca950fc94311baa49ad6b3694726b9cf', '81492f4f31d57a204c9312b707823fcc6c32c1ff6ea4d54842c0729ce5addfaf')]

def bootstrap(db):
    if not runtime_config.container_mode() or os.environ.get('YIFUN_DEMO_MODE') != '1':return False
    if runtime_config.owner_email() != CREDENTIALS[0][0] or not {item[0] for item in CREDENTIALS}.issubset(runtime_config.allowed_emails()):return False
    db.execute('CREATE TABLE IF NOT EXISTS demo_credential_migrations(name TEXT PRIMARY KEY)')
    if db.execute('SELECT 1 FROM demo_credential_migrations WHERE name=?',(MARKER,)).fetchone():return True
    # Existing authorized accounts only; never create or modify business records.
    users = [db.execute('SELECT id,status FROM employees WHERE email=?',(email,)).fetchone() for email,_,_ in CREDENTIALS]
    if any(user is None or user['status'] != 'active' for user in users):return False
    for (email,salt,digest),user in zip(CREDENTIALS,users):
        db.execute('UPDATE employees SET password_hash=?,salt=? WHERE id=?',(digest,salt,user['id']))
        db.execute('DELETE FROM employee_sessions WHERE user_id=?',(user['id'],))
        db.execute('DELETE FROM login_attempts WHERE email=?',(email,))
        db.execute('DELETE FROM account_recovery_links WHERE email=?',(email,))
        db.execute('DELETE FROM account_recovery_requests WHERE email=?',(email,))
    db.execute('INSERT INTO demo_credential_migrations(name) VALUES(?)',(MARKER,))
    return True
