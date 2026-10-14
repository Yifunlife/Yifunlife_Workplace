ALTER TABLE `quotation_history` ADD COLUMN `loss_reason` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `loss_note` text NOT NULL DEFAULT '';
--> statement-breakpoint
ALTER TABLE `quotation_history` ADD COLUMN `next_follow_up_at` text NOT NULL DEFAULT '';
--> statement-breakpoint
CREATE INDEX `quotation_history_loss_reason_idx` ON `quotation_history` (`loss_reason`);
