"""One-way reporting mirror from the standalone aftersales Worker, via private binding.
The source owns workflow changes. This mirror never receives passwords or file bytes.
"""
import hashlib,json,logging,os,threading,urllib.request,urllib.error
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import database,runtime_config,core

SOURCE='yifun-aftersales'
KEY='standalone_aftersales_sync_v1'
ZONE=ZoneInfo('Asia/Shanghai')
_lock=threading.Lock()

def stable(kind,key):return 'as-'+kind+'-'+hashlib.sha256(key.encode()).hexdigest()[:32]
def iso_ms(value):return datetime.fromtimestamp(int(value)/1000,timezone.utc).isoformat()
def slot(at=None):
    at=(at or datetime.now(timezone.utc)).astimezone(ZONE)
    if at.hour>=18:return at.date().isoformat()+'T18:00'
    if at.hour>=8:return at.date().isoformat()+'T08:00'
    return (at.date()-timedelta(days=1)).isoformat()+'T18:00'
def read_status(db):
    row=db.execute('SELECT value FROM settings WHERE key=?',(KEY,)).fetchone()
    return json.loads(row['value']) if row else {}
def status(db,user=None):
    s=read_status(db)
    return {**{k:v for k,v in s.items() if k!='etag'},'enabled':os.environ.get('YIFUN_AFTERSALES_SYNC')=='1',
            'schedule':['08:00','18:00'],'timezone':'Asia/Shanghai',
            'can_sync':bool(user and user['role'] in ('admin','ceo') and not runtime_config.read_only(user))}
def save_status(db,s):db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(KEY,json.dumps(s,ensure_ascii=False)))
def unique(rows,label):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Invalid '+label)
    result={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or len(row['id'])>200 or row['id'] in result:raise ValueError('Invalid or duplicate '+label+' id')
        result[row['id']]=row
    return result

def apply_snapshot(db,snapshot,actor):
    if snapshot.get('schemaVersion')!=1 or snapshot.get('source')!=SOURCE:raise ValueError('Unsupported aftersales snapshot')
    customers=unique(snapshot.get('customers'),'customer');stores=unique(snapshot.get('stores'),'store')
    requests=unique(snapshot.get('requests'),'request');items=unique(snapshot.get('items'),'item')
    # Validate the entire snapshot before writes; partial input must not archive valid records.
    for store in stores.values():
        if store.get('customer_id') not in customers:raise ValueError('Unknown customer')
    for request in requests.values():
        store=stores.get(request.get('store_id'))
        if not store or store['customer_id']!=request.get('customer_id'):raise ValueError('Invalid request ownership')
    for item in items.values():
        if item.get('request_id') not in requests or not isinstance(item.get('payload'),dict) or type(item.get('version')) is not int or item['version']<1:raise ValueError('Invalid work item')
        iso_ms(item['updated_at'])
    stamp=core.now();seen=set();changed=0
    for item in items.values():
        request=requests[item['request_id']];store=stores[request['store_id']];customer=customers[request['customer_id']];p=item['payload']
        cid=stable('customer',customer['id']);pid=stable('project',store['id']);tid=stable('ticket',item['id']);seen.add(tid)
        # Only explicit matching market IDs can link to group masters; names grant no identity or access.
        market=customer.get('market_id')
        linked=db.execute('SELECT id FROM customers WHERE id=?',(market,)).fetchone() if market else None
        if linked:cid=linked['id']
        else:
            db.execute('INSERT INTO customers(id,code,name,notes,created_by,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                       (cid,'AS-C-'+cid[-16:],customer.get('company') or '售后客户','来自独立售后系统',actor,stamp))
        market=store.get('market_id')
        linked=db.execute('SELECT id,customer_id FROM projects WHERE id=?',(market,)).fetchone() if market else None
        if linked and linked['customer_id']==cid:pid=linked['id']
        else:
            db.execute('INSERT INTO projects(id,code,name,customer_id,owner,notes,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                       (pid,'AS-P-'+pid[-16:],store.get('name') or '售后项目',cid,customer.get('sales_owner') or '', '来自独立售后系统；项目成员由管理员分配',stamp))
        old=db.execute('SELECT * FROM service_tickets WHERE id=?',(tid,)).fetchone();previous=json.loads(old['payload']) if old else {}
        if previous.get('sourceSystem') not in (None,SOURCE):raise ValueError('Ticket identity conflict')
        if previous.get('sourceVersion',0)>item['version']:continue
        stage=p.get('stage') or '审核';mapped={'采购':'生产采购','生产':'生产采购','品质检验':'生产采购','部门处理':'现场处理','负责人复核':'客户验收'}.get(stage,stage)
        payload={**previous,'id':tid,'projectId':pid,'product':p.get('product',''),'description':p.get('issue',''),'date':p.get('reported',''),
                 'deliveryDate':p.get('delivered',''),'region':p.get('country') or customer.get('country',''),'owner':p.get('owner',''),
                 'dueDate':p.get('planned',''),'actualDate':p.get('actual',''),'category':p.get('issueType','待分类'),'causeAnalysis':p.get('cause',''),
                 'stage':'关闭与复盘' if stage=='已关闭' else mapped,'dashboardStage':mapped,'dashboardSourceStage':'关闭与复盘' if stage=='已关闭' else mapped,
                 'executionMethod':p.get('executionMethod') or p.get('method',''),'safetyLevel':p.get('safetyLevel',''),
                 'costResponsibility':p.get('costResponsibility') or p.get('cost',''),'sourceSystem':SOURCE,'sourceId':item['id'],
                 'sourceVersion':item['version'],'sourceStage':stage,'sourceWorkNo':p.get('workNo',''),'sourceRemoved':False,
                 'sourceUrl':'https://yifun-aftersales.yifunlife.workers.dev/workspace'}
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
        if old and previous==payload and old['project_id']==pid:continue
        if old:db.execute('UPDATE service_tickets SET project_id=?,payload=?,version=version+1,updated_at=? WHERE id=?',(pid,encoded,iso_ms(item['updated_at']),tid))
        else:db.execute('INSERT INTO service_tickets(id,project_id,payload,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)',(tid,pid,encoded,actor,iso_ms(request['submitted_at']),iso_ms(item['updated_at'])))
        changed+=1
    # Retain an audit copy when the authoritative source removes a previously mirrored ticket.
    for old in db.execute('SELECT id,payload FROM service_tickets').fetchall():
        p=json.loads(old['payload'])
        if p.get('sourceSystem')==SOURCE and old['id'] not in seen and not p.get('sourceRemoved'):
            p.update(sourceRemoved=True,stage='关闭与复盘');db.execute('UPDATE service_tickets SET payload=?,version=version+1,updated_at=? WHERE id=?',(json.dumps(p,ensure_ascii=False),stamp,old['id']));changed+=1
    return {'items':len(items),'pending_requests':sum(r['status'] in ('pending','needs_info') for r in requests.values()),'changed':changed}

def refresh(manual=False,at=None):
    if os.environ.get('YIFUN_AFTERSALES_SYNC')!='1':return {'enabled':False}
    if not _lock.acquire(blocking=False):return {'busy':True}
    try:
        with database.connect() as db:previous=read_status(db)
        current_slot=slot(at)
        if not manual and previous.get('slot','')>=current_slot:return previous
        headers={'Accept':'application/json'}
        if previous.get('etag'):headers['If-None-Match']=previous['etag']
        request=urllib.request.Request('http://aftersales.yifun.internal/snapshot',headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=15) as response:
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ValueError('Aftersales response too large')
                snapshot=json.loads(raw);etag=response.headers.get('ETag')
        except urllib.error.HTTPError as error:
            if error.code!=304:raise
            snapshot=None;etag=previous.get('etag')
        with database.connect() as db:
            # Use current state after the network read; preserve other actors' changes.
            current=read_status(db)
            if snapshot is not None:
                actor=db.execute("SELECT id FROM employees WHERE email=? AND role='admin' AND status='active'",(runtime_config.owner_email(),)).fetchone()
                if not actor:actor=db.execute("SELECT id FROM employees WHERE role='admin' AND status='active' ORDER BY created_at LIMIT 1").fetchone()
                if not actor:raise ValueError('A group administrator is required before synchronization')
                counts=apply_snapshot(db,snapshot,actor['id'])
            else:counts={k:current.get(k,0) for k in ('items','pending_requests')};counts['changed']=0
            result={**current,**counts,'last_success':core.now(),'slot':current_slot,'etag':etag,'error':None}
            save_status(db,result)
        return result
    except Exception:
        logging.exception('Standalone aftersales synchronization failed')
        try:
            with database.connect() as db:
                s=read_status(db);s.update(error='售后同步暂未成功，保留上次成功的数据。',last_attempt=core.now());save_status(db,s)
        except Exception:logging.exception('Could not persist aftersales synchronization status')
        if manual:raise core.Problem('售后同步暂未成功，已保留上次数据，请稍后重试。',503)
        return {'error':'synchronization_failed'}
    finally:_lock.release()
