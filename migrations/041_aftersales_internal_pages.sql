-- Private records for the original after-sales internal pages only.
-- No writes to the group's procurement, factory, warehouse or finance ledgers.
CREATE TABLE af2_department_records(
 kind TEXT NOT NULL CHECK(kind IN ('installation','finance')),
 id TEXT NOT NULL,
 project_id TEXT NOT NULL REFERENCES projects(id),
 ticket_id TEXT NOT NULL REFERENCES service_tickets(id),
 payload TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,
 updated_by TEXT NOT NULL REFERENCES employees(id),
 updated_at TEXT NOT NULL,
 PRIMARY KEY(kind,id)
);
CREATE INDEX af2_department_project ON af2_department_records(project_id,kind);
