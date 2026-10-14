-- Seed only the existing explicitly synthetic shared order; never create commercial orders.
INSERT INTO engineering_tracking(id,project_id,stage,owner_id,delivery_date,progress_json,blocker_dept,blocker_reason,issue,updated_by,updated_at)
SELECT b.id,b.project_id,'生产中',
 (SELECT e.id FROM employees e JOIN project_members m ON m.employee_id=e.id WHERE m.project_id=b.project_id AND e.role='engineering' AND e.status='active' ORDER BY e.id LIMIT 1),
 date('now','+8 hours','+10 days'),
 '{"下单":100,"木工部":65,"软包部":25,"油漆部":45,"铁车间":80,"采购部":60,"安装":0}',
 '软包部','测试卡点：面料颜色待确认，影响软包生产','测试反馈：请协调面料确认后继续生产',
 (SELECT id FROM employees WHERE role='admin' AND status='active' ORDER BY id LIMIT 1),strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM order_baselines b JOIN projects p ON p.id=b.project_id
WHERE b.id='DEMO-FLOW-ORDER-3' AND p.id='DEMO-PROJECT-3' AND p.notes='共享测试项目'
 AND EXISTS(SELECT 1 FROM employees WHERE role='admin' AND status='active')
 AND NOT EXISTS(SELECT 1 FROM engineering_tracking WHERE id=b.id);
