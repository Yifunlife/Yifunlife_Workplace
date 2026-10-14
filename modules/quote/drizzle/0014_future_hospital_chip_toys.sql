UPDATE product_overrides
SET name = CASE product_id
  WHEN 'toys-Y40716' THEN '安定颗粒-屏显CT机（芯片款）'
  WHEN 'toys-Y40717' THEN '安神补脑剂-屏显CT机（芯片）'
  WHEN 'toys-Y40718' THEN '安慰剂-屏显CT机（芯片）'
  WHEN 'toys-Y40719' THEN '布灵布灵剂-屏显CT机（芯片）'
  WHEN 'toys-Y40720' THEN '超净泡泡剂-屏显CT机（芯片）'
  WHEN 'toys-Y40721' THEN '静思溶液-屏显CT机（芯片）'
  WHEN 'toys-Y40722' THEN '开心吐剂-屏显CT机（芯片）'
  WHEN 'toys-Y40723' THEN '膳食均衡胶囊-屏显CT机（芯片）'
  WHEN 'toys-Y40724' THEN '食欲促进剂-屏显CT机（芯片）'
  WHEN 'toys-Y40725' THEN '蔬菜补充剂-屏显CT机（芯片）'
  WHEN 'toys-Y40726' THEN '思乐含片-屏显CT机（芯片）'
  WHEN 'toys-Y40727' THEN '同理心增强剂-屏显CT机（芯片）'
  WHEN 'toys-Y40728' THEN '微量元素颗粒-屏显CT机（芯片）'
  WHEN 'toys-Y40729' THEN '消化酶颗粒-屏显CT机（芯片）'
  WHEN 'toys-Y40730' THEN '一颗见效丸-屏显CT机（芯片）'
  WHEN 'toys-Y40731' THEN '正念增强剂-屏显CT机（芯片）'
END,
category_1 = '配套产品',
category_2 = '未来医院区',
category_3 = '配套玩具',
updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE product_id IN (
  'toys-Y40716', 'toys-Y40717', 'toys-Y40718', 'toys-Y40719',
  'toys-Y40720', 'toys-Y40721', 'toys-Y40722', 'toys-Y40723',
  'toys-Y40724', 'toys-Y40725', 'toys-Y40726', 'toys-Y40727',
  'toys-Y40728', 'toys-Y40729', 'toys-Y40730', 'toys-Y40731'
);
