INSERT OR IGNORE INTO product_overrides (product_id, category_1, category_3, updated_at)
SELECT
  id,
  CASE WHEN family = '小玩具' THEN '配套产品' ELSE '模拟设备' END,
  CASE
    WHEN family = '小玩具' THEN '配套玩具'
    WHEN name LIKE '%凳%' THEN '配套产品'
    ELSE '主设备'
  END,
  strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM catalog_products;
--> statement-breakpoint
UPDATE product_overrides
SET category_3 = '配套玩具', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (SELECT id FROM catalog_products WHERE family = '小玩具');
--> statement-breakpoint
UPDATE product_overrides
SET category_3 = '配套产品', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (SELECT id FROM catalog_products WHERE family <> '小玩具' AND name LIKE '%凳%');
--> statement-breakpoint
UPDATE product_overrides
SET category_3 = '主设备', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE category_3 IS NULL OR TRIM(category_3) = '' OR category_3 = '未细分';
--> statement-breakpoint
UPDATE product_overrides
SET category_1 = CASE
  WHEN category_3 = '主设备' THEN '模拟设备'
  ELSE '配套产品'
END,
updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now');
--> statement-breakpoint
UPDATE product_overrides
SET category_2 = CASE
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category IN ('厨房区模拟设备', '厨房区域配套玩具')) THEN '厨房区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category IN ('未来厨房区模拟设备', '未来厨房区域配套玩具')) THEN '未来厨房区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '未来厨房区域英文版配套玩具') THEN '未来厨房区（英文版）'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category IN ('超市区模拟设备', '超市区域配套玩具')) THEN '超市区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '超市区域英文版配套玩具') THEN '超市区（英文版）'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category IN ('未来超市区模拟设备', '未来超市区域配套玩具')) THEN '未来超市区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '未来超市区域英文版配套玩具') THEN '未来超市区（英文版）'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category IN ('医院区模拟设备', '医院区域配套玩具')) THEN '医院区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '医院区域英文版配套玩具') THEN '医院区（英文版）'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '未来医院区域配套玩具') THEN '未来医院区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '未来医院区域配套玩具（英文版）') THEN '未来医院区（英文版）'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '果蔬采摘区域配套玩具') THEN '果蔬区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '种植采摘区域配套玩具' AND name LIKE '%芯片%') THEN '未来种植区'
  WHEN product_id IN (SELECT id FROM catalog_products WHERE category = '种植采摘区域配套玩具') THEN '种植区'
  ELSE category_2
END,
updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (
  SELECT id FROM catalog_products WHERE category IN (
    '厨房区模拟设备', '厨房区域配套玩具', '未来厨房区模拟设备', '未来厨房区域配套玩具', '未来厨房区域英文版配套玩具',
    '超市区模拟设备', '超市区域配套玩具', '超市区域英文版配套玩具', '未来超市区模拟设备', '未来超市区域配套玩具', '未来超市区域英文版配套玩具',
    '医院区模拟设备', '医院区域配套玩具', '医院区域英文版配套玩具', '未来医院区域配套玩具', '未来医院区域配套玩具（英文版）',
    '果蔬采摘区域配套玩具', '种植采摘区域配套玩具'
  )
);
