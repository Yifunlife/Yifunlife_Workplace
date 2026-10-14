CREATE TABLE IF NOT EXISTS `product_classifications` (
	`id` text PRIMARY KEY NOT NULL,
	`product_id` text NOT NULL,
	`level_1` text NOT NULL,
	`level_2` text NOT NULL,
	`level_3` text NOT NULL,
	`created_at` text DEFAULT '' NOT NULL,
	`updated_at` text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `product_classifications_product_id_idx`
	ON `product_classifications` (`product_id`);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `product_classifications_path_idx`
	ON `product_classifications` (`product_id`, `level_1`, `level_2`, `level_3`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `product_tags` (
	`product_id` text NOT NULL,
	`tag` text NOT NULL,
	PRIMARY KEY(`product_id`, `tag`)
);
--> statement-breakpoint
INSERT OR IGNORE INTO `product_classifications`
	(`id`, `product_id`, `level_1`, `level_2`, `level_3`, `created_at`, `updated_at`)
SELECT
	'classification-' || p.`id`,
	p.`id`,
	COALESCE(NULLIF(o.`major_category`, ''), CASE
		WHEN p.`category` IN ('消防区设备', '消防站区域配套玩具', '医院区域配套玩具', '医院区域英文版配套玩具', '医院区模拟设备', '未来医院区域配套玩具', '未来医院区域配套玩具（英文版）', '警察局区域配套玩具', '警察、工地设备', '工程、工地区域配套玩具', '航空区设备') THEN '职业体验 / Career Experience'
		WHEN p.`category` IN ('牧场区', '牧场区域配套玩具', '母鸡生蛋区域配套玩具', '种植采摘区域配套玩具', '果蔬采摘区域配套玩具', '鱼池区域配套玩具') THEN '农牧生活 / Agro-pastoral Life'
		WHEN p.`category` IN ('宠物医院、宠物之家区域配套玩具', '宠物医院、宠物之家区域配套玩具（英文版）', '萌宠、沐浴区模拟设备', '恐龙区设备', '恐龙区域配套玩具') THEN '动物世界 / Animal World'
		WHEN p.`category` IN ('赛车区域配套玩具', '赛车、修车区模拟设备', '修理店区域配套玩具', '洗车区', '洗车区域配套玩具') THEN '车生活 / Car Life'
		WHEN p.`category` IN ('排雷区设备', '沙池区域配套玩具', '沙池区设备', '积木、KTV设备') THEN '拼装手工 / Assemble by Hand'
		WHEN p.`category` IN ('摩天轮、旋转木马、小火车设备', '小球运动与水科技') THEN '机械传动 / Playground Scenes'
		WHEN p.`category` IN ('多媒体互动类', '数字体育运动', 'VR设备', '攀岩、运动区') THEN '多媒体互动 / Multimedia Interactivity'
		WHEN p.`category` = '(定制LOGO+0.27/双/定码定色/单码单色1000起，250双清箱)' THEN '零售（游玩必备） / Retail'
		ELSE '生活场景 / Lifestyle Scene'
	END),
	COALESCE(NULLIF(o.`category_1`, ''), CASE WHEN p.`family` = '小玩具' THEN '配套产品' ELSE '模拟设备' END),
	COALESCE(NULLIF(o.`category_2`, ''), NULLIF(p.`category`, ''), '未分类'),
	CURRENT_TIMESTAMP,
	CURRENT_TIMESTAMP
FROM `catalog_products` p
LEFT JOIN `product_overrides` o ON o.`product_id` = p.`id`;
--> statement-breakpoint
INSERT OR IGNORE INTO `product_tags` (`product_id`, `tag`)
SELECT
	p.`id`,
	COALESCE(
		NULLIF(o.`category_3`, ''),
		CASE
			WHEN p.`family` = '小玩具' THEN '配套玩具'
			WHEN (COALESCE(o.`name`, p.`name`) LIKE '%凳%'
				OR COALESCE(o.`name`, p.`name`) LIKE '%椅%'
				OR COALESCE(o.`name`, p.`name`) LIKE '%衣架%'
				OR COALESCE(o.`name`, p.`name`) LIKE '%挂钩%'
				OR COALESCE(o.`name`, p.`name`) LIKE '%购物车%'
				OR COALESCE(o.`name`, p.`name`) LIKE '%购物篮%') THEN '配套产品'
			ELSE '主设备'
		END
	)
FROM `catalog_products` p
LEFT JOIN `product_overrides` o ON o.`product_id` = p.`id`;
