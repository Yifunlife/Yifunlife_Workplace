ALTER TABLE warehouse_receipts ADD COLUMN cancelled_quantity INTEGER NOT NULL DEFAULT 0 CHECK(cancelled_quantity>=0 AND cancelled_quantity<=received_quantity);
ALTER TABLE warehouse_receipts ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE warehouse_receipts ADD COLUMN request_hash TEXT;
ALTER TABLE warehouse_records ADD COLUMN receipt_id TEXT REFERENCES warehouse_receipts(id);
ALTER TABLE warehouse_records ADD COLUMN warehouse_name TEXT;
ALTER TABLE warehouse_records ADD COLUMN storage_location TEXT;

-- Only a single historical batch has an unambiguous allocation. Preserve original
-- received quantities and record cancellations separately; never invent locations.
UPDATE warehouse_receipts SET
 cancelled_quantity=received_quantity-(SELECT received_quantity FROM order_items WHERE id=item_id),
 stocked_quantity=(SELECT stocked_quantity FROM order_items WHERE id=item_id),
 status= CASE WHEN (SELECT stocked_quantity FROM order_items WHERE id=item_id)>0
 AND (SELECT stocked_quantity=received_quantity FROM order_items WHERE id=item_id) THEN 'stocked'
 WHEN status='stocked' THEN 'passed' ELSE status END
WHERE (SELECT COUNT(*) FROM warehouse_receipts r WHERE r.item_id=warehouse_receipts.item_id)=1
 AND EXISTS(SELECT 1 FROM order_items i WHERE i.id=item_id AND i.received_quantity BETWEEN 0 AND warehouse_receipts.received_quantity AND i.stocked_quantity BETWEEN 0 AND i.received_quantity);

CREATE TRIGGER warehouse_receipt_quantity_guard BEFORE UPDATE ON warehouse_receipts
WHEN NEW.stocked_quantity>NEW.received_quantity-NEW.cancelled_quantity
BEGIN SELECT RAISE(ABORT,'仓库批次数量不一致'); END;

CREATE TABLE warehouse_receipt_actions (
 id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES warehouse_receipts(id),
 action TEXT NOT NULL CHECK(action IN ('passed','exception','resolve')),
 exception_type TEXT, exception_quantity INTEGER, note TEXT NOT NULL DEFAULT '',
 expected_revision INTEGER NOT NULL, request_hash TEXT NOT NULL,
 actor_id TEXT NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL, created_at TEXT NOT NULL
);
INSERT INTO warehouse_receipt_actions
 SELECT 'legacy-'||r.id,r.id, CASE WHEN r.status='exception' THEN 'exception' ELSE 'passed' END ,
 r.exception_type,r.exception_quantity,r.exception_notes,0,'legacy',w.actor_id,COALESCE(r.inspected_by,r.received_by),COALESCE(r.inspected_at,r.updated_at)
 FROM warehouse_receipts r JOIN warehouse_records w ON w.id=r.id WHERE r.inspected_at IS NOT NULL;
CREATE TRIGGER warehouse_receipt_action_guard BEFORE INSERT ON warehouse_receipt_actions
WHEN NOT EXISTS(SELECT 1 FROM warehouse_receipts r JOIN purchase_orders p ON p.id=r.order_id
 WHERE r.id=NEW.receipt_id AND p.archived_at IS NULL AND r.revision=NEW.expected_revision
 AND r.received_quantity>r.cancelled_quantity
 AND ((NEW.action IN ('passed','exception') AND r.status='pending_inspection')
 OR (NEW.action='resolve' AND r.status='exception' AND length(trim(NEW.note))>0))
 AND (NEW.action!='exception' OR (NEW.exception_type IN ('shortage','overage','wrong_item','damaged','specification','other') AND typeof(NEW.exception_quantity)='integer' AND NEW.exception_quantity BETWEEN 1 AND r.received_quantity-r.cancelled_quantity AND length(trim(NEW.note))>0)))
BEGIN SELECT RAISE(ABORT,'仓库验收状态已变化，请刷新核对'); END;
CREATE TRIGGER warehouse_receipt_action_apply AFTER INSERT ON warehouse_receipt_actions BEGIN
 UPDATE warehouse_receipts SET status= CASE WHEN NEW.action='resolve' THEN 'pending_inspection' ELSE NEW.action END ,
 exception_type= CASE WHEN NEW.action='exception' THEN NEW.exception_type ELSE NULL END ,
 exception_quantity= CASE WHEN NEW.action='exception' THEN NEW.exception_quantity ELSE NULL END ,
 exception_notes= CASE WHEN NEW.action='exception' THEN NEW.note ELSE '' END ,
 inspected_at= CASE WHEN NEW.action='resolve' THEN NULL ELSE NEW.created_at END ,
 inspected_by= CASE WHEN NEW.action='resolve' THEN NULL ELSE NEW.actor_name END ,
 revision=revision+1,updated_at=NEW.created_at WHERE id=NEW.receipt_id;
 INSERT INTO order_events(id,order_id,event_type,detail,actor_id,actor_name,created_at)
 SELECT NEW.id,order_id, CASE NEW.action WHEN 'resolve' THEN 'warehouse_exception_resolved' WHEN 'passed' THEN 'warehouse_inspection_passed' ELSE 'warehouse_exception' END ,
 CASE NEW.action WHEN 'resolve' THEN '异常已处理，等待仓库复验：' WHEN 'passed' THEN '仓库验收通过，等待入库' ELSE '仓库验收异常：' END ||NEW.note,NEW.actor_id,NEW.actor_name,NEW.created_at FROM warehouse_receipts WHERE id=NEW.receipt_id;
END;
CREATE TRIGGER warehouse_receipt_action_no_update BEFORE UPDATE ON warehouse_receipt_actions BEGIN SELECT RAISE(ABORT,'验收处理记录不可覆盖'); END;
CREATE TRIGGER warehouse_receipt_action_no_delete BEFORE DELETE ON warehouse_receipt_actions BEGIN SELECT RAISE(ABORT,'验收处理记录不可删除'); END;

-- All stock movements, including old API routes, must reference a passed batch.
CREATE TRIGGER warehouse_stock_batch_guard BEFORE INSERT ON warehouse_records
WHEN NEW.action='stocked' AND NOT EXISTS(SELECT 1 FROM warehouse_receipts r WHERE r.id=NEW.receipt_id AND r.item_id=NEW.item_id AND r.order_id=NEW.order_id AND r.status='passed'
 AND NEW.quantity<=r.received_quantity-r.cancelled_quantity-r.stocked_quantity
 AND length(trim(NEW.warehouse_name))>0 AND length(trim(NEW.storage_location))>0
 AND (r.stocked_quantity=0 OR (r.warehouse_name=NEW.warehouse_name AND r.storage_location=NEW.storage_location)))
BEGIN SELECT RAISE(ABORT,'仓库入库必须选择已验收批次及仓库库位'); END;
CREATE TRIGGER warehouse_stock_batch_apply AFTER INSERT ON warehouse_records WHEN NEW.action='stocked' BEGIN
 UPDATE warehouse_receipts SET stocked_quantity=stocked_quantity+NEW.quantity,
 status= CASE WHEN stocked_quantity+NEW.quantity=received_quantity-cancelled_quantity THEN 'stocked' ELSE 'passed' END ,
 warehouse_name=NEW.warehouse_name,storage_location=NEW.storage_location,stocked_at=NEW.created_at,stocked_by=NEW.actor_name,revision=revision+1,updated_at=NEW.created_at WHERE id=NEW.receipt_id;
END;

CREATE TABLE warehouse_correction_allocations (
 correction_id TEXT NOT NULL REFERENCES item_corrections(id), receipt_id TEXT NOT NULL REFERENCES warehouse_receipts(id),
 quantity INTEGER NOT NULL CHECK(quantity>0), PRIMARY KEY(correction_id,receipt_id)
);
CREATE TRIGGER item_correction_batch_guard BEFORE INSERT ON item_corrections WHEN NEW.action IN ('received','stocked') AND (
 (SELECT COALESCE(SUM(received_quantity-cancelled_quantity),0) FROM warehouse_receipts WHERE item_id=NEW.item_id)!=NEW.expected_received
 OR (SELECT COALESCE(SUM(stocked_quantity),0) FROM warehouse_receipts WHERE item_id=NEW.item_id)!=NEW.expected_stocked)
BEGIN SELECT RAISE(ABORT,'更正状态与历史批次不一致，请先核对批次数量'); END;
-- A SKU-level cancellation reverses the latest available batches first. These
-- allocations are appended, so neither receipt nor stock source records are erased.
CREATE TRIGGER item_correction_batch_apply AFTER INSERT ON item_corrections WHEN NEW.action IN ('received','stocked') BEGIN
 INSERT INTO warehouse_correction_allocations(correction_id,receipt_id,quantity)
 SELECT NEW.id,id,MIN(available,NEW.quantity-preceding) FROM (
   SELECT id, CASE NEW.action WHEN 'stocked' THEN stocked_quantity ELSE received_quantity-cancelled_quantity-stocked_quantity END AS available,
   COALESCE(SUM( CASE NEW.action WHEN 'stocked' THEN stocked_quantity ELSE received_quantity-cancelled_quantity-stocked_quantity END ) OVER (ORDER BY created_at DESC,rowid DESC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) AS preceding
   FROM warehouse_receipts WHERE item_id=NEW.item_id
 ) WHERE available>0 AND preceding<NEW.quantity;
 UPDATE warehouse_receipts SET
 cancelled_quantity=cancelled_quantity+ CASE WHEN NEW.action='received' THEN (SELECT quantity FROM warehouse_correction_allocations WHERE correction_id=NEW.id AND receipt_id=warehouse_receipts.id) ELSE 0 END ,
 stocked_quantity=stocked_quantity- CASE WHEN NEW.action='stocked' THEN (SELECT quantity FROM warehouse_correction_allocations WHERE correction_id=NEW.id AND receipt_id=warehouse_receipts.id) ELSE 0 END ,
 status= CASE WHEN NEW.action='received' AND stocked_quantity>0 AND received_quantity-cancelled_quantity-(SELECT quantity FROM warehouse_correction_allocations WHERE correction_id=NEW.id AND receipt_id=warehouse_receipts.id)=stocked_quantity THEN 'stocked'
 WHEN NEW.action='stocked' AND status='stocked' THEN 'passed' ELSE status END ,
 revision=revision+1,updated_at=NEW.created_at
 WHERE id IN (SELECT receipt_id FROM warehouse_correction_allocations WHERE correction_id=NEW.id);
END;
CREATE TRIGGER warehouse_correction_allocation_no_update BEFORE UPDATE ON warehouse_correction_allocations BEGIN SELECT RAISE(ABORT,'批次更正记录不可覆盖'); END;
CREATE TRIGGER warehouse_correction_allocation_no_delete BEFORE DELETE ON warehouse_correction_allocations BEGIN SELECT RAISE(ABORT,'批次更正记录不可删除'); END;

ALTER TABLE shipment_quantity_corrections ADD COLUMN requires_warehouse INTEGER NOT NULL DEFAULT 1 CHECK(requires_warehouse IN (0,1));
CREATE TRIGGER shipment_correction_insert_guard BEFORE INSERT ON shipment_quantity_corrections
WHEN (NEW.requires_warehouse=0 AND EXISTS(SELECT 1 FROM order_items WHERE id=NEW.item_id AND (received_quantity>0 OR stocked_quantity>0)))
 OR NEW.status!='pending' OR NEW.delta_quantity!=NEW.corrected_quantity-NEW.previous_quantity
 OR EXISTS(SELECT 1 FROM shipment_quantity_corrections WHERE shipment_id=NEW.shipment_id AND item_id=NEW.item_id AND status='pending')
 OR NOT EXISTS(SELECT 1 FROM shipment_items si JOIN order_items i ON i.id=si.item_id JOIN purchase_orders p ON p.id=i.order_id
 WHERE si.shipment_id=NEW.shipment_id AND si.item_id=NEW.item_id AND i.order_id=NEW.order_id AND p.archived_at IS NULL AND p.status!='completed'
 AND si.quantity+COALESCE((SELECT SUM(delta_quantity) FROM shipment_quantity_corrections WHERE shipment_id=NEW.shipment_id AND item_id=NEW.item_id AND status='applied'),0)=NEW.previous_quantity
 AND i.shipped_quantity+NEW.delta_quantity BETWEEN i.received_quantity AND i.quantity)
BEGIN SELECT RAISE(ABORT,'发货更正状态已变化或数量超出范围'); END;
CREATE TRIGGER shipment_correction_decision_guard BEFORE UPDATE ON shipment_quantity_corrections
WHEN OLD.status!='pending' OR NEW.status NOT IN ('applied','rejected')
 OR NEW.order_id!=OLD.order_id OR NEW.shipment_id!=OLD.shipment_id OR NEW.item_id!=OLD.item_id
 OR NEW.previous_quantity!=OLD.previous_quantity OR NEW.corrected_quantity!=OLD.corrected_quantity OR NEW.delta_quantity!=OLD.delta_quantity
 OR NEW.requires_warehouse!=OLD.requires_warehouse OR NEW.reason!=OLD.reason OR NEW.requested_by!=OLD.requested_by OR NEW.requested_at!=OLD.requested_at
 OR NEW.decided_by IS NULL OR NEW.decided_at IS NULL
 OR (NEW.status='applied' AND NOT EXISTS(SELECT 1 FROM order_items i JOIN purchase_orders p ON p.id=i.order_id
 WHERE i.id=NEW.item_id AND p.archived_at IS NULL AND p.status!='completed'
 AND i.shipped_quantity+NEW.delta_quantity BETWEEN i.received_quantity AND i.quantity
 AND NEW.previous_quantity=(SELECT quantity FROM shipment_items WHERE shipment_id=NEW.shipment_id AND item_id=NEW.item_id)+COALESCE((SELECT SUM(delta_quantity) FROM shipment_quantity_corrections WHERE shipment_id=NEW.shipment_id AND item_id=NEW.item_id AND status='applied'),0)))
BEGIN SELECT RAISE(ABORT,'发货更正状态已变化或数量超出范围'); END;
CREATE TRIGGER shipment_correction_apply AFTER UPDATE ON shipment_quantity_corrections BEGIN
 UPDATE order_items SET shipped_quantity=shipped_quantity+NEW.delta_quantity,
 workflow_stage= CASE WHEN shipped_quantity+NEW.delta_quantity=quantity THEN 'shipment_complete' WHEN workflow_stage='shipment_complete' THEN 'ready_to_ship' ELSE workflow_stage END
 WHERE id=NEW.item_id AND NEW.status='applied';
 UPDATE purchase_orders SET
 status= CASE WHEN NOT EXISTS(SELECT 1 FROM order_items WHERE order_id=NEW.order_id AND shipped_quantity<quantity) THEN 'shipped' ELSE 'ready_to_ship' END ,
 shipment_status= CASE WHEN NOT EXISTS(SELECT 1 FROM order_items WHERE order_id=NEW.order_id AND shipped_quantity>0) THEN 'none' WHEN NOT EXISTS(SELECT 1 FROM order_items WHERE order_id=NEW.order_id AND shipped_quantity<quantity) THEN 'complete' ELSE 'partial' END ,
 shipped_at= CASE WHEN NOT EXISTS(SELECT 1 FROM order_items WHERE order_id=NEW.order_id AND shipped_quantity>0) THEN NULL ELSE shipped_at END ,
 updated_at=NEW.decided_at WHERE id=NEW.order_id AND NEW.status='applied';
 INSERT INTO order_events(id,order_id,event_type,detail,actor_id,actor_name,created_at) VALUES
 (NEW.id,NEW.order_id, CASE NEW.status WHEN 'applied' THEN 'shipment_corrected' ELSE 'shipment_correction_rejected' END ,
 CASE NEW.status WHEN 'applied' THEN '更正发货数量：'||NEW.previous_quantity||' → '||NEW.corrected_quantity||' 件；' ELSE '驳回发货更正：' END ||NEW.reason||'；'||COALESCE(NEW.decision_note,''),NEW.decided_by,NEW.decided_by_name,NEW.decided_at);
END;
CREATE TRIGGER shipment_correction_no_delete BEFORE DELETE ON shipment_quantity_corrections BEGIN SELECT RAISE(ABORT,'发货更正记录不可删除'); END;
