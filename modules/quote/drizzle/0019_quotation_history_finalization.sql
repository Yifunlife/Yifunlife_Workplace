ALTER TABLE `quotation_history` ADD COLUMN `is_finalized` integer NOT NULL DEFAULT 0;
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `archived_at` text;
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `lineage_id` text;
--> statement-breakpoint
CREATE INDEX `quotation_history_archived_at_idx` ON `quotation_history` (`archived_at`);
--> statement-breakpoint
CREATE INDEX `quotation_history_lineage_id_idx` ON `quotation_history` (`lineage_id`);
