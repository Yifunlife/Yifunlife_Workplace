-- Existing names are retained for reference; they never grant account access.
ALTER TABLE customers ADD COLUMN created_by TEXT REFERENCES employees(id);
ALTER TABLE projects ADD COLUMN member_version INTEGER NOT NULL DEFAULT 1;
CREATE TABLE project_members (
  project_id TEXT NOT NULL REFERENCES projects(id),
  employee_id TEXT NOT NULL REFERENCES employees(id),
  assignment_role TEXT NOT NULL CHECK(assignment_role IN ('owner','member')),
  assigned_by TEXT NOT NULL REFERENCES employees(id),
  assigned_at TEXT NOT NULL,
  PRIMARY KEY(project_id,employee_id)
);
CREATE UNIQUE INDEX project_one_owner ON project_members(project_id) WHERE assignment_role='owner';
CREATE INDEX employee_projects ON project_members(employee_id,project_id);
ALTER TABLE toy_matching_drafts ADD COLUMN project_id TEXT REFERENCES projects(id);

UPDATE toy_matching_drafts SET project_id=json_extract(snapshot_json,'$.workspaceProjectId')
 WHERE json_valid(snapshot_json) AND json_extract(snapshot_json,'$.workspaceProjectId') IN (SELECT id FROM projects);
