-- Legacy split receipts may have stock/corrections recorded only at SKU level.
-- Keep those totals and require an explicit, audited allocation to real batches.
CREATE TABLE warehouse_batch_reconciliations (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES purchase_orders(id), item_id TEXT NOT NULL REFERENCES order_items(id),
 expected_received INTEGER NOT NULL, expected_stocked INTEGER NOT NULL,
 previous_json TEXT NOT NULL, allocations_json TEXT NOT NULL, reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 actor_id TEXT NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER warehouse_reconciliation_guard BEFORE INSERT ON warehouse_batch_reconciliations
WHEN NOT EXISTS(SELECT 1 FROM order_items i JOIN purchase_orders p ON p.id=i.order_id WHERE i.id=NEW.item_id AND i.order_id=NEW.order_id AND p.archived_at IS NULL AND i.received_quantity=NEW.expected_received AND i.stocked_quantity=NEW.expected_stocked)
 OR json_array_length(NEW.allocations_json)!=(SELECT COUNT(*) FROM warehouse_receipts WHERE item_id=NEW.item_id)
 OR (SELECT COUNT(DISTINCT json_extract(value,'$.id')) FROM json_each(NEW.allocations_json))!=json_array_length(NEW.allocations_json)
 OR EXISTS(SELECT 1 FROM json_each(NEW.allocations_json) a LEFT JOIN warehouse_receipts r ON r.id=json_extract(a.value,'$.id') AND r.item_id=NEW.item_id
 WHERE r.id IS NULL OR r.revision!=json_extract(a.value,'$.revision')
 OR json_type(a.value,'$.received')!='integer' OR json_type(a.value,'$.stocked')!='integer'
 OR json_extract(a.value,'$.received') NOT BETWEEN 0 AND r.received_quantity
 OR json_extract(a.value,'$.stocked') NOT BETWEEN 0 AND json_extract(a.value,'$.received'))
 OR (SELECT SUM(json_extract(value,'$.received')) FROM json_each(NEW.allocations_json))!=NEW.expected_received
 OR (SELECT SUM(json_extract(value,'$.stocked')) FROM json_each(NEW.allocations_json))!=NEW.expected_stocked
BEGIN SELECT RAISE(ABORT,'批次数量核对失败或状态已变化'); END;
CREATE TRIGGER warehouse_reconciliation_apply AFTER INSERT ON warehouse_batch_reconciliations BEGIN
 UPDATE warehouse_receipts SET
 cancelled_quantity=received_quantity-(SELECT json_extract(value,'$.received') FROM json_each(NEW.allocations_json) WHERE json_extract(value,'$.id')=warehouse_receipts.id),
 stocked_quantity=(SELECT json_extract(value,'$.stocked') FROM json_each(NEW.allocations_json) WHERE json_extract(value,'$.id')=warehouse_receipts.id),
 status= CASE WHEN (SELECT json_extract(value,'$.stocked')>0 AND json_extract(value,'$.stocked')=json_extract(value,'$.received') FROM json_each(NEW.allocations_json) WHERE json_extract(value,'$.id')=warehouse_receipts.id) THEN 'stocked' WHEN status='stocked' THEN 'pending_inspection' ELSE status END ,
 revision=revision+1,updated_at=NEW.created_at WHERE item_id=NEW.item_id;
 INSERT INTO order_events(id,order_id,event_type,detail,actor_id,actor_name,created_at) VALUES (NEW.id,NEW.order_id,'warehouse_reconciled','历史批次数量核对：'||NEW.reason,NEW.actor_id,NEW.actor_name,NEW.created_at);
END;
CREATE TRIGGER warehouse_reconciliation_no_update BEFORE UPDATE ON warehouse_batch_reconciliations BEGIN SELECT RAISE(ABORT,'批次核对记录不可覆盖'); END;
CREATE TRIGGER warehouse_reconciliation_no_delete BEFORE DELETE ON warehouse_batch_reconciliations BEGIN SELECT RAISE(ABORT,'批次核对记录不可删除'); END;
CREATE TRIGGER warehouse_stock_balance_guard BEFORE INSERT ON warehouse_records WHEN NEW.action='stocked' AND (
 (SELECT COALESCE(SUM(received_quantity-cancelled_quantity),0) FROM warehouse_receipts WHERE item_id=NEW.item_id)!=(SELECT received_quantity FROM order_items WHERE id=NEW.item_id)
 OR (SELECT COALESCE(SUM(stocked_quantity),0) FROM warehouse_receipts WHERE item_id=NEW.item_id)!=(SELECT stocked_quantity FROM order_items WHERE id=NEW.item_id))
BEGIN SELECT RAISE(ABORT,'仓库历史批次数量不一致，请先核对'); END;
