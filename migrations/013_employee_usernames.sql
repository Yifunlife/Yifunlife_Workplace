CREATE TABLE employee_login_names (
 employee_id TEXT PRIMARY KEY REFERENCES employees(id),
 username TEXT NOT NULL UNIQUE COLLATE NOCASE
);
