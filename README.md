# Yifunlife Workplace

完整集团看板部署在 https://yifunlife-workplace.yifunlife.workers.dev 。

## 2026-10-13 迁移记录

原账号 MarkFang 的 102 张数据表、427 条记录已迁入 Yifunlife Cloudflare，数据库逐项比对一致。四个原始 R2 存储桶对象总数为 0。

`backups/workplace-backup-20261013.enc` 为 AES-256-GCM 加密数据备份，包含数据库结构、记录和文件清单；不包含 Cloudflare 或 GitHub 凭据。解密密钥仅保存在迁移执行电脑的受限文件中，未上传 GitHub。

网站运行时数据存放 Cloudflare。GitHub 保存代码、结构、迁移备份，不作为在线数据库。代码更新不得重置业务数据。

镜像构建工作流使用临时凭据，构建后删除。发布前生成新的 Cloudflare 镜像仓库凭据，构建成功后更新 wrangler.jsonc 的镜像版本再部署。

原账号 Cloudflare Access 密码恢复入口尚未迁移，目标站已移除旧账号配置；账号密码及业务权限随数据库保留。
