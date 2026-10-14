UPDATE product_overrides
SET
  name = (
    SELECT name
    FROM catalog_products
    WHERE catalog_products.id = product_overrides.product_id
  ),
  category_1 = '配套产品',
  category_2 = '恐龙区',
  category_3 = '配套玩具',
  updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (
  'toys-Y40716', 'toys-Y40717', 'toys-Y40718', 'toys-Y40719',
  'toys-Y40720', 'toys-Y40721', 'toys-Y40722', 'toys-Y40723',
  'toys-Y40724', 'toys-Y40725', 'toys-Y40726', 'toys-Y40727',
  'toys-Y40728', 'toys-Y40729', 'toys-Y40730', 'toys-Y40731'
);
