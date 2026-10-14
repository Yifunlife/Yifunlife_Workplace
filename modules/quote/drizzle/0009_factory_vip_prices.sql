ALTER TABLE `catalog_products` ADD COLUMN `factory_price` real;
ALTER TABLE `catalog_products` ADD COLUMN `vip_price` real;
UPDATE `catalog_products` SET `vip_price` = `price` WHERE `vip_price` IS NULL;
