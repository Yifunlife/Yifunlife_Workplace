ALTER TABLE quotation_history ADD COLUMN final_amount real;
ALTER TABLE quotation_history ADD COLUMN final_currency text;
ALTER TABLE quotation_history ADD COLUMN confirmed_at text;
ALTER TABLE quotation_history ADD COLUMN confirmed_by text NOT NULL DEFAULT '';
ALTER TABLE quotation_history ADD COLUMN voided_at text;
ALTER TABLE quotation_history ADD COLUMN voided_by text NOT NULL DEFAULT '';
ALTER TABLE quotation_history ADD COLUMN void_reason text NOT NULL DEFAULT '';
