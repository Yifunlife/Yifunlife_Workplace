CREATE TABLE connected_sales (
 source_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL UNIQUE REFERENCES customers(id),
 project_id TEXT REFERENCES projects(id), payload TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 synced_at TEXT NOT NULL
);
CREATE TABLE connected_quotes (
 id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), payload TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, synced_at TEXT NOT NULL
);
CREATE TABLE connection_runs (
 source TEXT PRIMARY KEY, last_success TEXT, last_attempt TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', count INTEGER NOT NULL DEFAULT 0
);
