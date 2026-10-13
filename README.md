# YIFUN Workplace

Migration destination: Yifunlife/Yifunlife_Workplace and Cloudflare account 5a472d15dc37681abce4ab6e4eb152c3.

Run `python3 prepare_source.py` to restore the modules and migrations. Install dependencies with `pnpm install --frozen-lockfile`.

This source includes the compact two-row sales department layout. Business database and attachments are not stored in this repository.

Migration status: source prepared; deployment and business data migration pending. Existing recovery configuration must be replaced for the destination account before production deployment. Do not switch the original site until migration and access checks pass.


## 迁移进度（2026-10-13）

代码已迁入 Yifunlife 私有仓库，容器构建成功，Cloudflare 新站已部署。
新站：https://yifunlife-workplace.yifunlife.workers.dev
入口保持关闭，等待原账号数据库及附件完整迁移和核验。原站仍保留。
原账号 Access 恢复配置已移除，恢复入口需在新账号重新配置。
构建工作流使用短期镜像仓库凭据，构建后已删除；后续构建需重新签发。
