CREATE TABLE aftersales_expenses (
 id TEXT PRIMARY KEY,
 ticket_id TEXT NOT NULL REFERENCES service_tickets(id),
 project_id TEXT NOT NULL REFERENCES projects(id),
 category TEXT NOT NULL CHECK(category IN ('parts','freight','labor','travel','other')),
 amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
 currency TEXT NOT NULL CHECK(currency IN ('CNY','USD','EUR','SAR','AED','AUD')),
 record_date TEXT NOT NULL,
 reference TEXT NOT NULL UNIQUE,
 note TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL REFERENCES employees(id),
 created_at TEXT NOT NULL,
 voided_by TEXT REFERENCES employees(id),
 voided_at TEXT,
 void_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX aftersales_expenses_period ON aftersales_expenses(record_date,project_id);
CREATE TRIGGER aftersales_expense_keep_record BEFORE UPDATE ON aftersales_expenses
 WHEN NEW.id IS NOT OLD.id OR NEW.ticket_id IS NOT OLD.ticket_id OR NEW.project_id IS NOT OLD.project_id
 OR NEW.category IS NOT OLD.category OR NEW.amount_minor IS NOT OLD.amount_minor
 OR NEW.currency IS NOT OLD.currency OR NEW.record_date IS NOT OLD.record_date
 OR NEW.reference IS NOT OLD.reference OR NEW.note IS NOT OLD.note
 OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
 OR OLD.voided_at IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'费用原记录保留，请作废后重新登记'); END;
CREATE TRIGGER aftersales_expense_no_delete BEFORE DELETE ON aftersales_expenses
 BEGIN SELECT RAISE(ABORT,'售后费用记录不可删除'); END;
