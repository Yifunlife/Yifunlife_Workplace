# Yifunlife Workplace

完整集团看板部署在 https://yifunlife-workplace.yifunlife.workers.dev 。

## 2026-10-13 迁移记录

原账号 MarkFang 的 102 张数据表、427 条记录已迁入 Yifunlife Cloudflare，数据库逐项比对一致。四个原始 R2 存储桶对象总数为 0。

`backups/workplace-backup-20261013.enc` 为 AES-256-GCM 加密数据备份，包含数据库结构、记录和文件清单；不包含 Cloudflare 或 GitHub 凭据。解密密钥仅保存在迁移执行电脑的受限文件中，未上传 GitHub。

网站运行时数据存放 Cloudflare。GitHub 保存代码、结构、迁移备份，不作为在线数据库。代码更新不得重置业务数据。

主分支更新会触发 Deploy Workplace：权限测试 → 镜像构建 → 四个服务启动检查 → 推送镜像 → 发布 Worker 和容器 → 线上可用性检查。需在 GitHub Actions Secrets 设置 CLOUDFLARE_API_TOKEN；令牌仅授权目标 Cloudflare 账号所需的 Workers、Containers 和 R2 部署权限。未设置时流程明确失败，不会发布。构建失败不会修改当前线上版本；发布按顺序执行，不自动导入或重置数据库。线上检查仅覆盖可用性和匿名访问边界，不替代登录后的业务验收。

原账号 Cloudflare Access 密码恢复入口尚未迁移，目标站已移除旧账号配置；账号密码及业务权限随数据库保留。
