UPDATE product_overrides
SET category_1 = '配套产品',
    category_3 = '配套产品',
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (
  SELECT id
  FROM catalog_products
  WHERE name LIKE '%凳%'
     OR name LIKE '%椅%'
     OR name LIKE '%衣架%'
     OR name LIKE '%挂钩%'
     OR name LIKE '%购物车%'
     OR name LIKE '%购物篮%'
);
