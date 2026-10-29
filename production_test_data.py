"""Idempotent synthetic production examples restricted to the shared test project."""
import json
from datetime import date, timedelta
import core

MARKER='production_examples_20261029_v1'

def seed(db):
    db.execute('CREATE TABLE IF NOT EXISTS production_part_tracking(order_id TEXT PRIMARY KEY REFERENCES order_baselines(id),parts_json TEXT NOT NULL)')
    if db.execute('SELECT 1 FROM settings WHERE key=?',(MARKER,)).fetchone():return
    template=db.execute("SELECT b.* FROM order_baselines b JOIN projects p ON p.id=b.project_id WHERE p.id='DEMO-PROJECT-3' AND p.notes='共享测试项目' ORDER BY b.created_at LIMIT 1").fetchone()
    actor=db.execute("SELECT * FROM employees WHERE role='admin' AND status='active' ORDER BY id LIMIT 1").fetchone()
    if not template or not actor:return
    stamp=core.now(); today=date.today()
    examples=[('进行中与卡点', [100,80,65,40,60,75,0], {'paint':{'quantity':24,'progress':40},'upholstery':{'quantity':18,'progress':65},'metal':{'quantity':12,'progress':60},'house':{'progress':80}}, [('采购部','测试：面料待到货，请协调供应商交期'),('软包部','测试：面料未齐，软包收口暂缓')]),
              ('未开始与待登记',[100,0,0,None,0,20,0], {'paint':{'quantity':16,'progress':None},'upholstery':{'quantity':12,'progress':0},'metal':{'quantity':20,'progress':0},'house':{'progress':0}}, [('铁车间','测试：支架孔位待确认'),('工程部','测试：已收到尺寸复核需求，正在核对图纸')]),
              ('进度全部完成',[100,100,100,100,100,100,0], {'paint':{'quantity':32,'progress':100},'upholstery':{'quantity':20,'progress':100},'metal':{'quantity':16,'progress':100},'house':{'progress':100}}, [])]
    for index,(label,values,parts,feedback) in enumerate(examples,1):
        key=f'DEMO-PRODUCTION-20261029-{index}'
        quote=dict(db.execute('SELECT * FROM quotation_history WHERE id=?',(template['quote_id'],)).fetchone())
        quote['id']=key+'-QUOTE'
        quote['contract_no']=f'DEMO-PROD-Q-1029-{index}'
        if 'lineage_id' in quote:quote['lineage_id']=key+'-LINEAGE'
        if 'final_amount' in quote:quote['final_amount']=0.01
        columns=list(quote)
        db.execute('INSERT OR IGNORE INTO quotation_history('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[quote[k] for k in columns])
        db.execute('INSERT OR IGNORE INTO order_baselines(id,number,project_id,quote_id,kind,currency,agreed_minor,raw_snapshot,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,f'DEMO-PROD-1029-{index}',template['project_id'],quote['id'],template['kind'],template['currency'],1,json.dumps({'sharedDemo':True,'label':'生产测试：'+label}),actor['id'],stamp))
        progress=dict(zip(('下单','木工部','软包部','油漆部','铁车间','采购部','安装'),values))
        dept,reason=feedback[-1] if feedback else ('','')
        db.execute('INSERT OR IGNORE INTO engineering_tracking(id,project_id,stage,owner_id,delivery_date,progress_json,blocker_dept,blocker_reason,issue,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,template['project_id'],'生产中',actor['id'],(today+timedelta(days=3+index)).isoformat(),json.dumps(progress,ensure_ascii=False),dept,reason,'生产测试：'+label,actor['id'],stamp))
        db.execute('INSERT OR IGNORE INTO production_part_tracking VALUES(?,?)',(key,json.dumps(parts)))
        for dept,reason in feedback:
            after={'project_id':template['project_id'],'blocker_dept':dept,'blocker_reason':reason,'issue':'共享测试反馈，非真实生产问题'}
            core.audit(db,dict(actor),'engineering_tracking',key,'生产共享测试反馈',{'before':None,'after':after,'synthetic':True})
    db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(MARKER,stamp))
    core.audit(db,dict(actor),'demo',MARKER,'加入三笔生产测试订单',{'synthetic':True})
