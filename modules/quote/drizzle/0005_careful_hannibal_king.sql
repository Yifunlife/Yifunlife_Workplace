CREATE TABLE `catalog_products` (
	`id` text PRIMARY KEY NOT NULL,
	`sku` text NOT NULL,
	`name` text NOT NULL,
	`english_name` text DEFAULT '' NOT NULL,
	`category` text DEFAULT '' NOT NULL,
	`family` text DEFAULT '' NOT NULL,
	`price` real,
	`price_note` text DEFAULT '' NOT NULL,
	`usd_price` real,
	`unit` text DEFAULT '' NOT NULL,
	`specification` text DEFAULT '' NOT NULL,
	`brand` text DEFAULT '' NOT NULL,
	`material` text DEFAULT '' NOT NULL,
	`note` text DEFAULT '' NOT NULL,
	`image_key` text DEFAULT '' NOT NULL
);
