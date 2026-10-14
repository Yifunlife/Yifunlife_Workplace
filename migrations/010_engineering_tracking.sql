CREATE TABLE engineering_tracking (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES projects(id),
 stage TEXT NOT NULL CHECK(stage IN ('未排期','下单中','生产中','待安装','安装中','售后','未来订单')),
 owner_id TEXT REFERENCES employees(id),
 delivery_date TEXT,
 progress_json TEXT NOT NULL DEFAULT '{}',
 blocker_dept TEXT NOT NULL DEFAULT '',
 blocker_reason TEXT NOT NULL DEFAULT '',
 issue TEXT NOT NULL DEFAULT '',
 updated_by TEXT NOT NULL REFERENCES employees(id),
 updated_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX engineering_tracking_project ON engineering_tracking(project_id);
