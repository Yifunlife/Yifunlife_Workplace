"""Test integration: one account ledger shared by operations and CEO."""
import json
from pathlib import Path
import core
from marketing_reporting import ADVERTISING_EXPENSE_TYPES

def init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS marketing_accounts(id TEXT PRIMARY KEY,market TEXT NOT NULL,platform TEXT NOT NULL,name TEXT NOT NULL,owner_id TEXT REFERENCES employees(id));
    CREATE TABLE IF NOT EXISTS marketing_daily(account_id TEXT REFERENCES marketing_accounts(id),day TEXT NOT NULL,fans INTEGER NOT NULL,posts INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(account_id,day));
    CREATE TABLE IF NOT EXISTS marketing_test_contracts(id TEXT PRIMARY KEY,account_id TEXT REFERENCES marketing_accounts(id),day TEXT NOT NULL,amount_minor INTEGER NOT NULL,currency TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active');
    ''')
    if 'account_id' not in {r[1] for r in db.execute('PRAGMA table_info(marketing_spends)')}:
        db.execute('ALTER TABLE marketing_spends ADD COLUMN account_id TEXT REFERENCES marketing_accounts(id)')
    for a in json.loads((Path(__file__).parent/'account-inventory.json').read_text()):
        db.execute('INSERT OR IGNORE INTO marketing_accounts(id,market,platform,name) VALUES(?,?,?,?)',(str(a['id']),a['market'],a['platform'],a['name']))
    db.commit()

def save(db,user,kind,p):
    core.permit(user,'admin','ceo')
    account=core.need(db,'marketing_accounts',p.get('account_id'))
    if kind=='snapshot':
        day=core.day(p.get('day'))
        for k in ('fans','posts'):
            if type(p.get(k)) is not int or p[k]<0:raise core.Problem('粉丝数和发布数必须为非负整数')
        old=db.execute('SELECT * FROM marketing_daily WHERE account_id=? AND day=?',(account['id'],day)).fetchone()
        if old:
            if p.get('version')!=old['version']:raise core.Problem('记录已更新，请刷新',409)
            db.execute('UPDATE marketing_daily SET fans=?,posts=?,version=version+1 WHERE account_id=? AND day=?',(p['fans'],p['posts'],account['id'],day))
        else:db.execute('INSERT INTO marketing_daily(account_id,day,fans,posts) VALUES(?,?,?,?)',(account['id'],day,p['fans'],p['posts']))
        return {'account_id':account['id'],'day':day}
    if kind=='test_contract':
        day=core.day(p.get('day'));amount=core.money(p.get('amount'),zero=True)
        if p.get('currency') not in ('CNY','USD'):raise core.Problem('请选择测试币种')
        if p.get('status','active') not in ('active','void'):raise core.Problem('无效状态')
        key=core.text(p.get('id'),'测试合同编号')
        db.execute('INSERT INTO marketing_test_contracts VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET account_id=excluded.account_id,day=excluded.day,amount_minor=excluded.amount_minor,currency=excluded.currency,status=excluded.status',(key,account['id'],day,amount,p['currency'],p.get('status','active')))
        return {'id':key}
    raise core.Problem('未知测试操作')

def report(db,start,end,today,currency='CNY'):
    year=today[:4]+'-01-01';month=today[:7]+'-01'
    output=[]
    for raw in db.execute('SELECT a.*,e.name owner FROM marketing_accounts a LEFT JOIN employees e ON a.owner_id=e.id ORDER BY CAST(a.id AS INTEGER)'):
        a=dict(raw);key=a['id']
        snaps=[dict(r) for r in db.execute('SELECT * FROM marketing_daily WHERE account_id=? ORDER BY day',(key,))]
        snapshot=lambda day:next((x['fans'] for x in reversed(snaps) if x['day']<=day),None)
        previous=lambda day:next((x['fans'] for x in reversed(snaps) if x['day']<day),None)
        total=snapshot(today);mb=previous(month);tb=previous(today)
        spends=[dict(r) for r in db.execute("SELECT * FROM marketing_spends WHERE account_id=? AND status='active' AND currency=?",(key,currency))]
        spend=lambda lo,hi,ads=False:sum(x['amount_minor'] for x in spends if lo<=x['record_date']<=hi and (not ads or x['expense_type'] in ADVERTISING_EXPENSE_TYPES))
        orders=[dict(r) for r in db.execute("SELECT * FROM marketing_test_contracts WHERE account_id=? AND status='active' AND currency=?",(key,currency))]
        sales=lambda lo,hi:sum(x['amount_minor'] for x in orders if lo<=x['day']<=hi)
        a.update(fans=total,month_gain=total-mb if total is not None and mb is not None else None,today_gain=total-tb if total is not None and tb is not None else None,month_posts=sum(x['posts'] for x in snaps if month<=x['day']<=today),cost=spend(start,end),sales=sales(start,end),month_cost=spend(month,today),month_sales=sales(month,today),annual_ads=spend(year,today,True),monthly_ads=spend(month,today,True))
        a['ratio']=a['sales']/a['cost'] if a['cost'] else None
        output.append(a)
    markets=[]
    for name in ('内贸','外贸'):
        rows=[a for a in output if a['market']==name];m={'market':name,'account_count':len(rows)}
        for k in ('cost','sales','month_cost','month_sales','annual_ads','monthly_ads','month_posts'):m[k]=sum(a[k] for a in rows)
        m['month_ratio']=m['month_sales']/m['month_cost'] if m['month_cost'] else None
        markets.append(m)
    return {'test_mode':True,'currency':currency,'period':{'from':start,'to':end,'timezone':'Asia/Shanghai'},'today':today,'accounts':output,'markets':markets,'unassigned_spend_count':db.execute("SELECT COUNT(*) FROM marketing_spends WHERE status='active' AND account_id IS NULL").fetchone()[0]}
