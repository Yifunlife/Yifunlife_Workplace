CREATE TABLE `app_users` (
  `email` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `password_hash` text NOT NULL,
  `password_salt` text NOT NULL,
  `role` text DEFAULT 'employee' NOT NULL,
  `status` text DEFAULT 'pending' NOT NULL,
  `created_at` text NOT NULL,
  `updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `password_reset_tokens` (
  `token_hash` text PRIMARY KEY NOT NULL,
  `email` text NOT NULL,
  `expires_at` text NOT NULL,
  `created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `password_reset_tokens_email_idx` ON `password_reset_tokens` (`email`);
