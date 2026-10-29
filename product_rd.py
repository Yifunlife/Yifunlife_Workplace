"""Product theme register shared by the R&D dashboard."""
from datetime import date
import core as c
import column_permissions as cp
STAGES=['新品讨论','低保真设计','协作与3D确认','工厂打样','样品验收','产品标准化','产品上架']
def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS product_rd_themes(id TEXT PRIMARY KEY,title TEXT NOT NULL,group_name TEXT NOT NULL,owner_id TEXT NOT NULL,stage INTEGER NOT NULL DEFAULT 0,planned_date TEXT NOT NULL,listed_date TEXT NOT NULL DEFAULT '',visual TEXT NOT NULL DEFAULT '',software TEXT NOT NULL DEFAULT '',print_status TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,created_by TEXT NOT NULL)''')
def report(db,user):
    cp.require(db,user,'center-product_rd')
    items=[dict(r) for r in db.execute('SELECT t.*,e.name owner FROM product_rd_themes t LEFT JOIN employees e ON e.id=t.owner_id ORDER BY t.group_name,t.planned_date,t.title')]
    return {'items':items,'stages':STAGES,'can_write':cp.level(db,user,'center-product_rd')>=2,'employees':[dict(r) for r in db.execute("SELECT e.id,e.name FROM employees e JOIN center_members m ON m.employee_id=e.id WHERE m.center='product_rd' AND e.status='active' ORDER BY e.name")]}
def save(db,user,p):
    import centers
    centers.require_center(db,user,'product_rd')
    cp.require(db,user,'center-product_rd',True)
    title=c.text(p.get('title'),'设计主题',limit=200);group=p.get('group_name');owner=p.get('owner_id')
    if group not in ('研发一组','研发二组'):raise c.Problem('请选择研发小组')
    if not db.execute("SELECT 1 FROM center_members m JOIN employees e ON e.id=m.employee_id WHERE m.center='product_rd' AND m.employee_id=? AND e.status='active'",(owner,)).fetchone():raise c.Problem('请选择已分配到产品研发中心的在职员工')
    try:
        stage=int(p.get('stage',0));planned=date.fromisoformat(p.get('planned_date','')).isoformat();listed=date.fromisoformat(p.get('listed_date','')).isoformat() if p.get('listed_date') else ''
    except (ValueError,TypeError):raise c.Problem('请填写有效的阶段和日期')
    if stage not in range(7):raise c.Problem('研发阶段无效')
    if (stage==6)!=bool(listed):raise c.Problem('上架阶段必须填写实际上架日期；未上架阶段请清空实际上架日期')
    if listed and listed>date.today().isoformat():raise c.Problem('实际上架日期不能晚于今天')
    print_status=c.text(p.get('print_status',''),'3D确认情况',False,1000)
    if stage>=3 and print_status!='确认通过':raise c.Problem('下单打样前，请将3D打印确认情况设为“确认通过”')
    ident=p.get('id') or c.uid();before=db.execute('SELECT * FROM product_rd_themes WHERE id=?',(ident,)).fetchone()
    if p.get('id') and not before:raise c.Problem('主题已不存在，请刷新',404)
    values=(title,group,owner,stage,planned,listed,c.text(p.get('visual',''),'品牌视觉',False,1000),c.text(p.get('software',''),'软件协作',False,1000),print_status,c.text(p.get('note',''),'跟进记录',False,4000),c.now())
    if before:db.execute('UPDATE product_rd_themes SET title=?,group_name=?,owner_id=?,stage=?,planned_date=?,listed_date=?,visual=?,software=?,print_status=?,note=?,updated_at=? WHERE id=?',(*values,ident))
    else:db.execute('INSERT INTO product_rd_themes(title,group_name,owner_id,stage,planned_date,listed_date,visual,software,print_status,note,updated_at,id,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(*values,ident,user['id']))
    import centers
    centers.event(db,user,'product_rd_themes',ident,'更新研发主题' if before else '创建研发主题',dict(before) if before else {},dict(db.execute('SELECT * FROM product_rd_themes WHERE id=?',(ident,)).fetchone()))
    return {'ok':True,'id':ident}


def seed_examples(db):
    """One-time labelled fixtures for the existing shared test deployment."""
    import os,secrets
    from datetime import datetime
    from zoneinfo import ZoneInfo
    marker='product_rd_examples_20261029_v1'
    if os.environ.get('YIFUN_DEMO_MODE')!='1' or db.execute('SELECT 1 FROM settings WHERE key=?',(marker,)).fetchone():return
    actor=db.execute("SELECT * FROM employees WHERE role='admin' AND status='active' ORDER BY id LIMIT 1").fetchone()
    if not actor:return
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date();stamp=c.now()
    titles=['互动装置','桌面产品','配件系列','智能终端','展示模块','新品概念']
    stages=[2,3,1,4,5,0]
    for i,title in enumerate(titles):
        member=f'DEMO-RD-MEMBER-{i+1}';name='测试研发成员 '+chr(65+i);group='研发一组' if i<3 else '研发二组';stage=stages[i]
        db.execute('INSERT OR IGNORE INTO employees(id,email,name,role,status,password_hash,salt,created_at) VALUES(?,?,?,?,?,?,?,?)',(member,f'rd-test-{i+1}@example.invalid',name,'engineering','active',secrets.token_hex(32),secrets.token_hex(16),stamp))
        db.execute('INSERT OR IGNORE INTO center_members(employee_id,center) VALUES(?,?)',(member,'product_rd'))
        for done in (False,True):
            ident=f'DEMO-RD-20261029-{i+1}-'+('DONE' if done else 'ACTIVE')
            month=[1,3,5,7,9,today.month][i] if done else today.month
            planned=today.replace(month=month,day=15 if done else 28).isoformat();listed=today.replace(month=month,day=min(today.day,15)).isoformat() if done else ''
            visual='已完成视觉资料交接' if done or stage>=3 else '视觉方案确认中' if stage==2 else '待交接'
            software='已完成软件资料交接' if done or stage>=3 else '交互逻辑确认中' if stage==2 else '待交接'
            printed='确认通过' if done or stage>=3 else '待确认' if stage==2 else '待启动'
            note='共享测试数据，非真实研发业务。'+('已完成样品验收与标准化，上架记录用于验证年度及月度统计。' if done else ['确认新品定位和功能范围','补充低保真设计资料','等待3D打印结构确认','跟进工厂样品交期','记录样品验收结果','补齐图纸、物料及产品标准资料'][stage])
            db.execute('INSERT OR IGNORE INTO product_rd_themes(id,title,group_name,owner_id,stage,planned_date,listed_date,visual,software,print_status,note,updated_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,'【测试】'+title+(' · 已上架' if done else ' · 在研'),group,member,6 if done else stage,planned,listed,visual,software,printed,note,stamp,actor['id']))
    db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(marker,stamp))
    c.audit(db,dict(actor),'demo',marker,'添加产品研发共享测试主题',{'synthetic':True,'members':6,'active':6,'listed':6})
