"""Actual company-borne aftersales expenses, by posting date and currency."""
from collections import defaultdict
from datetime import date,datetime
from zoneinfo import ZoneInfo
import json
import core as c
import project_access as access

CATEGORIES={'parts':'配件','freight':'运输','labor':'人工','travel':'差旅','other':'其他'}
CURRENCIES=('CNY','USD','EUR','SAR','AED','AUD')
READERS=('admin','ceo','aftersales','finance')
WRITERS=('admin','ceo','aftersales')

def save(db,user,p):
    c.permit(user,*WRITERS)
    ticket=access.require(db,user,'service_tickets',p.get('ticket_id'))
    if json.loads(ticket['payload']).get('costResponsibility') in ('客户承担','供应商承担'):
        raise c.Problem('该工单已登记为客户或供应商承担，请先核对费用归属；这里只登记公司承担部分')
    category=p.get('category');currency=p.get('currency')
    if category not in CATEGORIES or currency not in CURRENCIES:raise c.Problem('请选择费用类别及币种')
    amount=c.money(p.get('amount'))
    day=c.day(p.get('record_date'))
    if day>datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat():raise c.Problem('实际费用日期不能晚于今天')
    reference=c.text(p.get('reference'),'费用编号／凭证号',limit=200)
    if db.execute('SELECT 1 FROM aftersales_expenses WHERE reference=?',(reference,)).fetchone() or db.execute('SELECT 1 FROM project_expenses WHERE reference=?',(reference,)).fetchone():
        raise c.Problem('费用编号／凭证号已登记，请核对，避免重复计入')
    key=c.uid()
    db.execute('INSERT INTO aftersales_expenses(id,ticket_id,project_id,category,amount_minor,currency,record_date,reference,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (key,ticket['id'],ticket['project_id'],category,amount,currency,day,reference,c.text(p.get('note',''),'说明',required=False),user['id'],c.now()))
    c.audit(db,user,'aftersales_expense',key,'登记公司承担的售后费用',{'ticket_id':ticket['id'],'currency':currency,'amount_minor':amount})
    return {'ok':True,'id':key}

def void(db,user,p):
    c.permit(user,*WRITERS)
    record=c.need(db,'aftersales_expenses',p.get('id'))
    access.require(db,user,'service_tickets',record['ticket_id'])
    if record['voided_at']:raise c.Problem('此费用已作废，请刷新',409)
    reason=c.text(p.get('reason'),'作废原因')
    db.execute('UPDATE aftersales_expenses SET voided_at=?,voided_by=?,void_reason=? WHERE id=?',(c.now(),user['id'],reason,record['id']))
    c.audit(db,user,'aftersales_expense',record['id'],'作废售后费用',{'reason':reason})
    return {'ok':True}

def report(db,projects,end):
    end=date.fromisoformat(end) if isinstance(end,str) else end
    start=end.replace(month=1,day=1).isoformat();month=end.replace(day=1).isoformat();cutoff=end.isoformat()
    projects={p['id']:p for p in projects} if not isinstance(projects,dict) else projects
    records=[];references=set()
    # The legacy expense category explicitly represents company aftersales parts.
    for row in db.execute("SELECT * FROM project_expenses WHERE category='aftersales' AND record_date BETWEEN ? AND ?",(start,cutoff)):
        r=dict(row)
        if r['project_id'] not in projects:continue
        references.add(r['reference'])
        records.append({'id':r['id'],'source':'project_expenses','ticket_id':None,'project_id':r['project_id'],'project_name':projects[r['project_id']]['name'],
            'category':'parts','category_label':'售后补件（费用登记）','minor':r['amount_minor'],'currency':r['currency'],'date':r['record_date'],'reference':r['reference'],'note':r['note']})
    for row in db.execute('SELECT * FROM aftersales_expenses WHERE voided_at IS NULL AND record_date BETWEEN ? AND ? ORDER BY record_date DESC,created_at DESC',(start,cutoff)):
        r=dict(row)
        if r['project_id'] not in projects or r['reference'] in references:continue
        references.add(r['reference'])
        records.append({'id':r['id'],'source':'aftersales_expenses','ticket_id':r['ticket_id'],'project_id':r['project_id'],'project_name':projects[r['project_id']]['name'],
            'category':r['category'],'category_label':CATEGORIES[r['category']],'minor':r['amount_minor'],'currency':r['currency'],'date':r['record_date'],'reference':r['reference'],'note':r['note']})
    annual=defaultdict(int);monthly=defaultdict(int)
    for r in records:
        annual[r['currency']]+=r['minor']
        if r['date']>=month:monthly[r['currency']]+=r['minor']
    def amounts(values):return [{'currency':currency,'minor':minor} for currency,minor in sorted(values.items())]
    records.sort(key=lambda r:(r['date'],r['reference']),reverse=True)
    return {'from':start,'month_from':month,'to':cutoff,'annual':amounts(annual),'monthly':amounts(monthly),
        'record_count':len(records),'monthly_count':sum(r['date']>=month for r in records),'records':records,
        'note':'按公司实际承担的费用及实际费用日期统计，含已关闭工单；不同币种分别汇总。售后费用登记与原费用登记中的售后补件按凭证号去重；采购单、库存数量及客户／供应商承担部分不自动计入。'}
