"""Read-only CEO finance analysis. The finance switch gates every ledger value."""
from collections import defaultdict
from datetime import timedelta
import core


def amounts(values):
    return [{'currency': c, 'minor': n} for c, n in sorted(values.items())]


def report(db, baselines, projects, start, end, day_of, include_stock=True):
    enabled = core.setting(db, 'finance_enabled') == '1'
    contracts = [b for b in baselines if day_of(b['created_at']) and day_of(b['created_at']) <= end]
    ids = {b['id'] for b in contracts}
    entries = [dict(r) for r in db.execute('SELECT * FROM customer_financial_entries')
               if r['baseline_id'] in ids and r['record_date'] <= end.isoformat()] if enabled else []
    def balance_rows(cutoff):
        rows = []
        for b in contracts:
            if day_of(b['created_at']) > cutoff:
                continue
            sums = defaultdict(int)
            for e in entries:
                if e['baseline_id'] == b['id'] and e['record_date'] <= cutoff.isoformat():
                    sums[e['kind']] += e['amount_minor']
            net = b['agreed_minor'] + sums['surcharge'] - sums['credit']
            remaining = net - sums['receipt']
            rows.append({k: b[k] for k in ('id','number','project_id','project_name','currency','agreed_minor')}
                        | {'receipt': sums['receipt'] if enabled else None,
                           'credit': sums['credit'] if enabled else None,
                           'surcharge': sums['surcharge'] if enabled else None,
                           'net_minor': net if enabled else None,
                           'remaining_minor': remaining if enabled else None})
        return rows
    rows = balance_rows(end)
    project_rows = []
    for p in projects:
        for currency in sorted({b['currency'] for b in rows if b['project_id'] == p['id']}):
            linked = [b for b in rows if b['project_id'] == p['id'] and b['currency'] == currency]
            entry = {'project_id': p['id'], 'project_name': p['name'], 'customer_name': p['customer_name'],
                     'customer_id': p['customer_id'], 'currency': currency, 'stage': p['stage'],
                     'contract_minor': sum(b['agreed_minor'] for b in linked), 'order_ids': [b['id'] for b in linked]}
            for field in ('receipt','credit','surcharge','net_minor','remaining_minor'):
                entry[field] = sum(b[field] for b in linked) if enabled else None
            entry['receivable_minor'] = sum(max(0,b['remaining_minor']) for b in linked) if enabled else None
            entry['customer_credit_minor'] = sum(max(0,-b['remaining_minor']) for b in linked) if enabled else None
            entry['received_ratio'] = round(entry['receipt']/entry['net_minor']*100,1) if enabled and entry['net_minor']>0 else None
            budget = core.row(db,'SELECT * FROM project_budgets WHERE project_id=? AND currency=?',(p['id'],currency)) if enabled else None
            entry['budget_minor'] = budget['amount_minor'] if budget else None
            entry['estimated_profit_minor'] = entry['net_minor']-budget['amount_minor'] if budget else None
            entry['estimated_margin'] = round(entry['estimated_profit_minor']/entry['net_minor']*100,1) if budget and entry['net_minor']>0 else None
            project_rows.append(entry)
    summary = []
    for currency in sorted({b['currency'] for b in rows}):
        linked = [p for p in project_rows if p['currency'] == currency]
        summary.append({'currency': currency, 'contract_minor': sum(p['contract_minor'] for p in linked),
                        'receipt': sum(p['receipt'] for p in linked) if enabled else None,
                        'receivable_minor': sum(p['receivable_minor'] for p in linked) if enabled else None,
                        'customer_credit_minor': sum(p['customer_credit_minor'] for p in linked) if enabled else None})
    # Only finance-confirmed settlements are payables. An estimated item subtotal is not a payable.
    suppliers = []
    if enabled:
        project_ids = {p['id'] for p in projects}
        for r in db.execute('''SELECT o.id,o.po_number,o.order_date,o.created_at,s.name supplier_name,x.project_id,x.purpose,
            z.currency,z.payable_cents,z.finance_confirmed
            FROM purchase_orders o JOIN suppliers s ON s.id=o.supplier_id
            LEFT JOIN procurement_context x ON x.order_id=o.id LEFT JOIN order_settlements z ON z.order_id=o.id
            WHERE o.archived_at IS NULL'''):
            if (r['project_id'] not in project_ids and not (include_stock and r['purpose']=='stock')) or not day_of(r['created_at']) or day_of(r['created_at'])>end:
                continue
            paid = db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM financial_entries WHERE order_id=? AND kind='payment' AND record_date<=?",(r['id'],end.isoformat())).fetchone()[0]
            extra = db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM financial_entries WHERE order_id=? AND kind='cost' AND record_date<=?",(r['id'],end.isoformat())).fetchone()[0]
            payable = r['payable_cents'] if r['finance_confirmed'] else None
            suppliers.append(dict(r) | {'paid_minor': paid,'extra_cost_minor': extra,
                             'remaining_minor': max(0,payable-paid) if payable is not None else None,
                             'overpaid_minor': max(0,paid-payable) if payable is not None else None})
    # Six month-end snapshots, with the final point ending at the selected date.
    month = end.replace(day=1)
    months = []
    for _ in range(6):
        months.insert(0,month)
        month=(month-timedelta(days=1)).replace(day=1)
    trend = []
    for month in months:
        next_month=(month.replace(day=28)+timedelta(days=4)).replace(day=1)
        cutoff=min(end,next_month-timedelta(days=1))
        snapshot=balance_rows(cutoff)
        for currency in sorted({b['currency'] for b in rows}):
            linked=[b for b in snapshot if b['currency']==currency]
            trend.append({'month':month.strftime('%Y-%m'),'as_of':cutoff.isoformat(),'currency':currency,
                          'contract_minor':sum(b['agreed_minor'] for b in linked),
                          'receipt':sum(b['receipt'] for b in linked) if enabled else None,
                          'receivable_minor':sum(max(0,b['remaining_minor']) for b in linked) if enabled else None})
    risks=[]
    if enabled:
        for b in rows:
            if b['remaining_minor']<0:
                risks.append({'project_id':b['project_id'],'title':'客户贷方余额待核对','detail':b['number'],'target':'baseline','target_id':b['id']})
        for s in suppliers:
            if s['remaining_minor'] is None or s['overpaid_minor']:
                risks.append({'project_id':s['project_id'],'title':'采购结算待确认' if s['remaining_minor'] is None else '供应商超付待核对','detail':s['po_number'],'target':'procurement','target_id':s['id']})
    inventory=[dict(r) for r in db.execute('''SELECT l.category,COUNT(DISTINCT b.product_id) sku_count FROM
        (SELECT location_id,product_id,SUM(quantity) quantity FROM stock_movements GROUP BY location_id,product_id HAVING SUM(quantity)>0) b
        JOIN warehouse_locations l ON l.id=b.location_id GROUP BY l.category''')]
    return {'enabled':enabled,'as_of':end.isoformat(),'summary':summary,'projects':project_rows,'orders':rows,
            'suppliers':suppliers,'supplier_due_minor':sum(s['remaining_minor'] for s in suppliers if s['remaining_minor'] is not None) if enabled else None,
            'unknown_supplier_count':sum(s['remaining_minor'] is None for s in suppliers) if enabled else None,
            'risks':risks if enabled else None,'risk_project_count':len({r['project_id'] for r in risks if r['project_id']}) if enabled else None,
            'trend':trend,'inventory':inventory,'inventory_value_minor':None,
            'inventory_note':'库存数量已接入；期初价值、计价方法和成本分摊待核定，尚不能计算库存价值。',
            'payment_plan_note':'尚未登记客户分期到期日与供应商付款计划，不能据余额判断逾期或预付款。'}


def export_csv(data, tab):
    import csv
    import io
    from decimal import Decimal
    if tab not in ('overview','finance'):
        raise core.Problem('请选择经营总况或财务资金分析')
    money=lambda n:'暂未接入' if n is None else Decimal(n)/100
    if tab=='finance':
        f=data['finance']
        rows=[['项目','币种','累计合同金额','累计已收款','待收款','客户贷方余额','Credit','补价','成本预算','预计利润']]
        rows += [[p['project_name'],p['currency']]+[money(p[k]) for k in ('contract_minor','receipt','receivable_minor','customer_credit_minor','credit','surcharge','budget_minor','estimated_profit_minor')] for p in f['projects']]
        rows += [[],['供应商付款'],['供应商','采购单','币种','已付款','待付款','额外成本（独立）']]
        rows += [[s['supplier_name'],s['po_number'],s['currency'] or 'CNY',money(s['paid_minor']),money(s['remaining_minor']),money(s['extra_cost_minor'])] for s in f['suppliers']]
        if not f['enabled']:rows.append(['财务暂未开放'])
        rows += [[],['近六个月月末累计趋势'],['月份','币种','累计合同','累计已收','待收款']]
        rows += [[r['month'],r['currency'],money(r['contract_minor']),money(r['receipt']),money(r['receivable_minor'])] for r in f['trend']]
        rows += [[],['库存价值','待核定'],['资料说明',f['payment_plan_note']],['预计利润说明','按同币种净合同金额减当前成本预算计算，不代表实际利润']]
    else:
        rows=[['项目编号','项目名称','客户','阶段','负责人','交付进度（%）','期限','期限依据','异常数量']]
        rows += [[p['code'],p['name'],p['customer_name'],p['stage'],p['owner'],p['progress'] if p['progress'] is not None else '暂无交付需求',p['due_date'] or '待安排',p['due_source'],p['exception_count']] for p in data['projects']]
        rows += [[],['本期已下单明细'],['订单','项目','类型','币种','金额','下单时间']]
        rows += [[b['number'],b['project_name'],'增项' if b['kind']=='addition' else '原单',b['currency'],money(b['agreed_minor']),b['created_at']] for b in data['period_orders']]
        rows += [[],['异常明细'],['项目','问题','负责人','逾期天数']]
        rows += [[e['project_name'],e['title'],e['owner'],e['overdue_days'] if e['overdue_days'] is not None else '待处理'] for e in data['exceptions']]
    scope=next((p['name'] for p in data['project_options'] if p['id']==data['selected_project']),'全部项目')
    rows += [[],['统计开始',data['period']['from'],'截止',data['period']['to'],'时区',data['period']['timezone']],['项目范围',scope],['导出说明','各币种分别统计；项目状态为当前状态；账款按截止日期计算。']]
    output=io.StringIO(newline='');writer=csv.writer(output)
    for row in rows:
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip(' \t\r\n').startswith(('=','+','-','@')) else v for v in row])
    return output.getvalue().encode('utf-8-sig')
