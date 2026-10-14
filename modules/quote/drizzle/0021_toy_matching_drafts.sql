CREATE TABLE `toy_matching_drafts` (
  `id` text PRIMARY KEY NOT NULL,
  `created_by` text NOT NULL,
  `name` text NOT NULL,
  `snapshot_json` text NOT NULL,
  `created_at` text NOT NULL,
  `updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `toy_matching_drafts_created_by_updated_at_idx`
  ON `toy_matching_drafts` (`created_by`, `updated_at`);
