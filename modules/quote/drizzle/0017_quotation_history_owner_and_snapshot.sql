ALTER TABLE `quotation_history` ADD COLUMN `created_by` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `snapshot_json` text;
--> statement-breakpoint
CREATE INDEX `quotation_history_created_by_generated_at_idx`
  ON `quotation_history` (`created_by`, `generated_at`);
