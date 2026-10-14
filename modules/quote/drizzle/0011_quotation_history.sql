CREATE TABLE `quotation_history` (
	`id` text PRIMARY KEY NOT NULL,
	`contract_no` text NOT NULL,
	`project_name` text NOT NULL,
	`generated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `quotation_history_generated_at_idx` ON `quotation_history` (`generated_at`);
