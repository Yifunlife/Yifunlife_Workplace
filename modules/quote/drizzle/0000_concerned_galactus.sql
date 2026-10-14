CREATE TABLE `catalog_categories` (
	`id` text PRIMARY KEY NOT NULL,
	`level` integer NOT NULL,
	`parent_key` text DEFAULT '' NOT NULL,
	`name` text NOT NULL,
	`created_at` text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE `product_overrides` (
	`product_id` text PRIMARY KEY NOT NULL,
	`name` text,
	`price` text,
	`image_url` text,
	`category_1` text,
	`category_2` text,
	`category_3` text,
	`color_tag` text,
	`has_screen` integer DEFAULT false NOT NULL,
	`is_recommended` integer DEFAULT false NOT NULL,
	`updated_at` text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE `product_recommendations` (
	`product_id` text NOT NULL,
	`related_product_id` text NOT NULL,
	PRIMARY KEY(`product_id`, `related_product_id`)
);
