PRAGMA foreign_keys = ON;

ALTER TABLE suppliers ADD COLUMN region TEXT NOT NULL DEFAULT '';
ALTER TABLE suppliers ADD COLUMN payment_account TEXT NOT NULL DEFAULT '';
ALTER TABLE suppliers ADD COLUMN notes TEXT NOT NULL DEFAULT '';

CREATE TABLE supplier_number_sequence (
  name TEXT PRIMARY KEY,
  prefix TEXT NOT NULL,
  current_value INTEGER NOT NULL CHECK (current_value >= 0)
);
INSERT INTO supplier_number_sequence (name, prefix, current_value) VALUES ('supplier', 'SP', 1045);

CREATE TABLE supplier_products (
  id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  product_type TEXT NOT NULL CHECK (product_type IN ('配件类', '电气类', '安全防护类', '成品设备类', '定制加工类')),
  product_name TEXT NOT NULL,
  usual_specification TEXT NOT NULL DEFAULT '',
  unit TEXT NOT NULL DEFAULT '',
  default_unit_price REAL,
  production_cycle TEXT NOT NULL DEFAULT '',
  transport_method TEXT NOT NULL DEFAULT '',
  arrival_time TEXT NOT NULL DEFAULT '',
  settlement_method TEXT NOT NULL DEFAULT '',
  special_invoice_tax TEXT NOT NULL DEFAULT '',
  ordinary_invoice_tax TEXT NOT NULL DEFAULT '',
  order_required_materials TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (supplier_id, product_name, usual_specification)
);
CREATE INDEX supplier_products_supplier_id_idx ON supplier_products(supplier_id);

ALTER TABLE order_items ADD COLUMN unit TEXT NOT NULL DEFAULT '';
-- Historical supplier seed data intentionally excluded from the shared source.
