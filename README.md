# Yifunlife Workplace

完整集团看板部署在 https://yifunlife-workplace.yifunlife.workers.dev 。

## 2026-10-13 迁移记录

原账号 MarkFang 的 102 张数据表、427 条记录已迁入 Yifunlife Cloudflare，数据库逐项比对一致。四个原始 R2 存储桶对象总数为 0。

`backups/workplace-backup-20261013.enc` 为 AES-256-GCM 加密数据备份，包含数据库结构、记录和文件清单；不包含 Cloudflare 或 GitHub 凭据。解密密钥仅保存在迁移执行电脑的受限文件中，未上传 GitHub。

网站运行时数据存放 Cloudflare。GitHub 保存代码、结构、迁移备份，不作为在线数据库。代码更新不得重置业务数据。

主分支更新会触发 Deploy Workplace：权限测试 → 镜像构建 → 四个服务启动检查 → 推送镜像 → 发布 Worker 和容器 → 线上可用性检查。需在 GitHub Actions Secrets 设置 CLOUDFLARE_API_TOKEN；令牌仅授权目标 Cloudflare 账号所需的 Workers、Containers 和 R2 部署权限。未设置时流程明确失败，不会发布。构建失败不会修改当前线上版本；发布按顺序执行，不自动导入或重置数据库。线上检查仅覆盖可用性和匿名访问边界，不替代登录后的业务验收。

原账号 Cloudflare Access 密码恢复入口尚未迁移，目标站已移除旧账号配置；账号密码及业务权限随数据库保留。

## 独立售后系统自动汇总

集团总看板通过 Cloudflare 私有服务绑定 `AFTERSALES_REPORTING` 读取 `yifun-aftersales` 的 `AftersalesReporting` 入口。每天上海时间 **08:00、18:00** 同步；复用已有一分钟调度检查时段，成功时段写入持久数据库，失败保留旧数据并重试。看板的 30 秒页面刷新仅读取集团已同步数据，不会轮询售后源。管理员／CEO 可用“立即同步”主动更新。

正式工单按稳定来源编号新增或更新，关闭状态随源系统变化；待检查申请单独计数，不提前当作正式工单。客户与项目优先使用明确的市场编号关联，无明确关联时创建有来源标识的独立记录，不按相同名称合并或自动授予成员权限。同步工单在集团端只读，流程修改仍在独立售后工作台办理。

页面显示最近成功同步时间、正式工单数量、待检查数量和失败状态。服务入口不导出密码、会话、邀请链接、图片或视频。预算、估算与费用承担标签不当作已发生的财务费用。尚在浏览器临时保存的业务记录不在同步范围。

验证：`python3 scripts/test_aftersales_cloud.py`，覆盖时间边界、幂等更新、状态及关闭同步、异常快照拒绝、失败保留数据、来源权限和旧工作流隔离。
