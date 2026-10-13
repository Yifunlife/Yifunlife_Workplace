"""Clearly labelled, synthetic records for the private shared test deployment."""
import json
import os
from datetime import datetime, timedelta, timezone
import core


def insert(db, table, values):
    columns = ','.join('"' + key + '"' for key in values)
    db.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))


def seed(db, user):
    if os.environ.get('YIFUN_DEMO_MODE') != '1': return
    if db.execute("SELECT 1 FROM settings WHERE key='shared_demo_seed_v1'").fetchone(): return
    if db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]:
        raise RuntimeError('Refusing to mix demonstration records into an existing business database')
    today = datetime.now(timezone(timedelta(hours=8))).date()
    day, stamp = today.isoformat(), core.now()
    for index in range(1, 4):
        customer, project = f'DEMO-CUSTOMER-{index}', f'DEMO-PROJECT-{index}'
        insert(db, 'customers', dict(id=customer, code=f'DEMO-C{index:03}', name=f'模拟客户 {index}',
            contact='模拟联系人', email=f'customer-{index}@example.invalid', notes='共享测试数据，非正式业务资料', created_at=stamp, created_by=user['id']))
        insert(db, 'projects', dict(id=project, code=f'DEMO-P{index:03}', name=['模拟内贸乐园项目','模拟海外设备项目','模拟配件交付项目'][index-1],
            customer_id=customer, location='模拟项目地点', owner=user['name'], notes='共享测试项目', created_at=stamp))
        insert(db, 'work_tasks', dict(id=f'DEMO-TASK-{index}', project_id=project, kind=['task','installation','issue'][index-1],
            title=['模拟报价核对','模拟安装计划','模拟现场反馈'][index-1], owner_id=user['id'], due_date=(today+timedelta(days=index)).isoformat(),
            status=['planned','planned','open'][index-1], description='用于查看页面与业务关联的模拟记录', created_by=user['id'], created_at=stamp, updated_at=stamp))
        insert(db, 'design_tasks', dict(id=f'DEMO-DESIGN-{index}', number=f'DEMO-D{index:03}', project_id=project,
            title=f'模拟方案设计 {index}', task_type='方案设计', brief='模拟项目设计需求', requested_date=day,
            due_date=(today+timedelta(days=7)).isoformat(), owner_id=user['id'], created_by=user['id'], created_at=stamp, updated_at=stamp))
        insert(db, 'crm_leads', dict(id=f'DEMO-LEAD-{index}', name=f'模拟来源线索 {index}', company=f'模拟公司 {index}', contact='模拟联系人',
            source=['抖音 · SUPER TADA','Instagram · 乐园号','小红书 · 工厂号'][index-1], owner_id=user['id'], next_date=day,
            next_action='模拟跟进事项', notes='非真实客户线索', customer_id=customer, created_by=user['id'], created_at=stamp, updated_at=stamp))
    for index in range(1, 7):
        insert(db, 'catalog_products', dict(id=f'DEMO-PRODUCT-{index}', sku=f'DEMO-SKU-{index:03}', name=f'模拟游乐配件 {index}',
            english_name=f'Demo component {index}', category='测试产品', price=100+index*50, usd_price=20+index*5,
            unit='件', specification='仅用于共享测试', note='模拟产品和模拟价格'))
        insert(db, 'stock_movements', dict(id=f'DEMO-STOCK-{index}', product_id=f'DEMO-PRODUCT-{index}', quantity=20+index*5,
            kind='opening', note='模拟期初库存', actor_id=user['id'], created_at=stamp, location_id='unassigned'))
    insert(db, 'suppliers', dict(id='DEMO-SUPPLIER-1', code='DEMO-S001', name='模拟供应商', contact_name='模拟联系人',
        contact_info='supplier@example.invalid', purchaser_name=user['name'], created_at=stamp, updated_at=stamp, notes='非正式供应商'))
    core.create_po(db, {**user, 'role':'purchasing'}, dict(purpose='stock', supplierId='DEMO-SUPPLIER-1', orderDate=day,
        requiredShipDate=(today+timedelta(days=14)).isoformat(), items=[dict(productId='DEMO-PRODUCT-1', quantity=3, unitPrice='150', productType='配件类')],
        internalRequirements='模拟备货采购，仅用于测试'))
    ticket = dict(id='DEMO-SERVICE-001', projectId='DEMO-PROJECT-3', deliveryLineId=None, date=day, product='模拟游乐配件 1', productEn='Demo component',
        description='模拟售后检查事项', descriptionEn='', category='产品检查', causeAnalysis='模拟原因待核对', causeAnalysisEn='', causeCategory='待确认',
        solution='模拟处理计划', solutionEn='', handling='待处理', followUpDate='', followUpResult='', summary='', summaryEn='', repeated='否',
        needsImprovement='否', suggestion='', owner=user['name'], stage='接收反馈', dueDate=(today+timedelta(days=5)).isoformat(), lastUpdated=day,
        source='模拟测试', notes='非真实售后记录', partsUsed=[], history=[dict(at=stamp, action='建立模拟售后单', note='共享测试')])
    insert(db, 'service_tickets', dict(id=ticket['id'], project_id='DEMO-PROJECT-3', payload=json.dumps(ticket,ensure_ascii=False),
        created_by=user['id'], created_at=stamp, updated_at=stamp))
    month = today.replace(day=1)
    for account in db.execute('SELECT id,market,platform FROM marketing_accounts'):
        index = int(account['id'])
        db.execute('UPDATE marketing_accounts SET owner_id=? WHERE id=?', (user['id'], account['id']))
        insert(db, 'marketing_daily', dict(account_id=account['id'], day=(month-timedelta(days=1)).isoformat(), fans=index*1000, posts=0))
        for offset in range(today.day):
            current = (month+timedelta(days=offset)).isoformat()
            insert(db, 'marketing_daily', dict(account_id=account['id'], day=current, fans=index*1000+(offset+1)*(index+7), posts=1 if index%3 else 2))
        for suffix, current, amount in [('month',day,5000+index*1000),('annual',today.replace(month=1,day=1).isoformat(),10000+index*1000)]:
            if suffix=='annual' and current==day: continue
            insert(db, 'marketing_spends', dict(id=f'DEMO-SPEND-{suffix}-{index}', number=f'DEMO-AD-{suffix}-{index:03}', record_date=current,
                channel=account['platform'], expense_type='广告投放', amount_minor=amount, currency='CNY', activity='模拟投放', region=account['market'],
                owner_id=user['id'], note='模拟广告费用', created_by=user['id'], created_at=stamp, updated_at=stamp, account_id=account['id']))
        if index%4:
            insert(db, 'marketing_test_contracts', dict(id=f'DEMO-CONTRACT-{index}', account_id=account['id'], day=day, amount_minor=(5000+index*1000)*5, currency='CNY'))
    core.shadow_user(db,user)
    insert(db, 'settings', dict(key='shared_demo_seed_v1', value=stamp))
    core.audit(db, user, 'demo', 'shared-test-v1', '初始化共享模拟资料', {'synthetic':True})
