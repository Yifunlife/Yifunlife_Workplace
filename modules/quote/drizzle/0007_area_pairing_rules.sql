CREATE TABLE `area_pairing_rules` (
  `area` text PRIMARY KEY NOT NULL,
  `config_json` text NOT NULL,
  `updated_at` text DEFAULT '' NOT NULL
);
