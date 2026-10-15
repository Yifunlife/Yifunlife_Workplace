"""Read-only procurement reporting over authorized shared purchase records."""
import json
from collections import defaultdict
import core as c
import project_access as access


def report(db,user,projects,today,project=None):
    year=today[:4];month=today[:7]
    finance=c.setting(db,'finance_enabled')=='1' and user['role'] in ('admin','ceo','finance')
    suppliers={r['id']:dict(r) for r in db.execute('SELECT * FROM suppliers')}
    lines=defaultdict(list)
    for r in db.execute('SELECT * FROM order_items'):lines[r['order_id']].append(dict(r))
    settlements={r['order_id']:dict(r) for r in db.execute('SELECT * FROM order_settlements')} if finance else {}
    paid=defaultdict(int)
    if finance:
        for r in db.execute("SELECT order_id,SUM(amount_cents) amount FROM financial_entries WHERE kind='payment' GROUP BY order_id"):paid[r['order_id']]=r['amount'] or 0
    orders=[];annual=defaultdict(lambda:{'name':'','orders':0,'units':defaultdict(float),'amount':0,'unknown_amount':0})
    for row in db.execute('SELECT p.*,x.project_id FROM purchase_orders p LEFT JOIN procurement_context x ON x.order_id=p.id WHERE p.archived_at IS NULL'):
        o=dict(row)
        if not access.visible_order(db,user,o['id']) or (project and o['project_id']!=project):continue
        items=lines[o['id']];supplier=suppliers.get(o['supplier_id'],{})
        terms={}
        try:terms=json.loads(o.get('commercial_terms_json') or '{}')
        except (ValueError,TypeError):pass
        currency=terms.get('currency') or 'CNY'
        # Use confirmed payable amounts; item subtotals are not assumed tax-inclusive.
        settlement=settlements.get(o['id'],{})
        amount=settlement.get('payable_cents') if settlement.get('finance_confirmed') else None
        subtotal=round(sum(i['amount'] for i in items)*100)
        units=defaultdict(float)
        for i in items:units[i.get('unit') or '未注明单位']+=i['quantity']
        complete=o['status']=='completed'
        quantity=sum(i['quantity'] for i in items);shipped=sum(i['shipped_quantity'] for i in items);received=sum(i['received_quantity'] for i in items);stocked=sum(i['stocked_quantity'] for i in items)
        due=o.get('promised_ship_date') or o.get('required_ship_date')
        late=bool(due and due<today and shipped<quantity)
        rejected=any(i['acceptance_status']=='rejected' for i in items)
        stage='待确认' if o['status']=='pending_confirmation' else '待到货' if received<quantity else '待验收' if stocked<quantity else '待对账'
        p=projects.get(o.get('project_id'),{})
        out={'id':o['id'],'number':o['po_number'],'project_id':o['project_id'],'project':p.get('name') or o['project_name'] or '备货采购','sales':p.get('owner') or '待登记','engineer':'待登记','supplier':supplier.get('name','待登记'),'supplier_id':o['supplier_id'],'owner':o['purchaser_name'],'stage':stage,'completed':complete,'late':late,'rejected':rejected,'due':due,'estimated_ship':o.get('estimated_ship_date'),'arrival':None,'note':o.get('production_note') or o.get('delivery_change_reason') or '', 'currency':currency,'amount':amount,'subtotal':subtotal,'paid':paid[o['id']] if finance else None,'units':dict(units),'items':[],'order_date':o['order_date']}
        for i in items:
            out['items'].append({'id':i['id'],'name':i['product_name'],'unit':i.get('unit') or '未注明单位','quantity':i['quantity'],'ordered':i['quantity'],'shipped':i['shipped_quantity'],'received':i['received_quantity'],'completed':i['stocked_quantity'],'actual':i.get('received_at'),'issue':'验收未通过，待处理' if i['acceptance_status']=='rejected' else '发货逾期' if late and i['shipped_quantity']<i['quantity'] else out['note'] or '—'})
        out['items'].sort(key=lambda i:(i['received']>=i['quantity'],i['name']))
        orders.append(out)
        if year+'-01-01'<=o['order_date']<=today:
            a=annual[o['supplier_id']];a['name']=out['supplier'];a['orders']+=1
            for unit,q in units.items():a['units'][unit]+=q
            if currency=='CNY':a['amount']+=amount or 0;a['unknown_amount']+=amount is None
    current=[o for o in orders if not o['completed']]
    yearly=[o for o in orders if year+'-01-01'<=o['order_date']<=today and o['currency']=='CNY']
    monthly=[o for o in yearly if o['order_date'].startswith(month)]
    def metric_total(rows):return sum(o['amount'] or 0 for o in rows) if finance and all(o['amount'] is not None for o in rows) else None
    total=metric_total(yearly);payments=sum(o['paid'] or 0 for o in yearly) if finance else None
    annual_rows=[dict(v,units=dict(v['units'])) for v in annual.values()]
    annual_rows.sort(key=lambda a:(-a['orders'],a['name']))
    return {'orders':current,'annual_suppliers':annual_rows,'year':year,'today':today,'year_amount':total,'month_amount':metric_total(monthly),'paid_rate':round(payments/total*100,1) if total and payments is not None else None,'remaining':sum(max(o['amount']-(o['paid'] or 0),0) for o in yearly) if total is not None and finance else None,'finance':finance,'notices':['金额为已确认的人民币含税应付金额，资料未齐或无财务权限时不计算。','到货预计日期、付款到期计划与项目工程师尚未结构化登记；发货承诺不作为预计到货时间。','数量按单位分别汇总，不累加不同单位。供应商年度采购量按单位展示；跨单位按采购订单笔数排名。','当前订单包含待对账订单；已完成及已归档采购订单不列入当前跟进。']}
