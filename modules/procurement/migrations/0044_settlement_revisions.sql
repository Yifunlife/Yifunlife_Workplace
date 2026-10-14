ALTER TABLE order_settlements ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE order_settlements ADD COLUMN finance_change_id TEXT;
CREATE TRIGGER settlement_revision AFTER UPDATE ON order_settlements WHEN NEW.revision=OLD.revision BEGIN
 UPDATE order_settlements SET revision=revision+1 WHERE order_id=NEW.order_id;
END;
