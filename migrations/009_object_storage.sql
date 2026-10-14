ALTER TABLE operation_files ADD COLUMN object_key TEXT;
CREATE UNIQUE INDEX operation_files_object_key ON operation_files(object_key) WHERE object_key IS NOT NULL;
