CREATE TABLE `kitchen_packages` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`description` text DEFAULT '' NOT NULL,
	`config_json` text NOT NULL,
	`updated_at` text DEFAULT '' NOT NULL
);
--> statement-breakpoint
ALTER TABLE `product_overrides` ADD `stock` integer;
