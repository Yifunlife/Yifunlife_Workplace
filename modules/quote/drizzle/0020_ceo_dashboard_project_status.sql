ALTER TABLE `quotation_history` ADD COLUMN `project_status` text NOT NULL DEFAULT 'quoted';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `status_updated_at` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `customer_name` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `last_follow_up_at` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `quote_valid_until` text NOT NULL DEFAULT '';
--> statement-breakpoint
CREATE INDEX `quotation_history_project_status_idx` ON `quotation_history` (`project_status`);
