ALTER TABLE crm_leads ADD COLUMN customer_grade TEXT NOT NULL DEFAULT '' CHECK(customer_grade IN ('','A','B','C'));
CREATE TABLE marketing_lead_allocations(id TEXT PRIMARY KEY,lead_id TEXT NOT NULL REFERENCES crm_leads(id),owner_id TEXT NOT NULL REFERENCES employees(id),assigned_by TEXT NOT NULL REFERENCES employees(id),assigned_at TEXT NOT NULL);
CREATE INDEX marketing_allocation_month ON marketing_lead_allocations(owner_id,assigned_at);
