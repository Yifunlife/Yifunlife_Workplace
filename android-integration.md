# 安卓软件中心接入契约 v2

## 当前边界

网站、数据库、任务状态机、配置同步、Agent 诊断、事件队列、告警与签名回调已实现。设备安装、重启、应用日志和内容下载执行器仍明确阻断，等待真实设备、APK 和厂商信息后适配。业务授权配置不等同于游戏执行端已经实施许可控制。

## 设备接口

均使用 HTTPS POST JSON。绑定接口使用一次性接入码，其余设备接口使用 `Authorization: Bearer <设备私有凭证>`；设备凭证不能访问员工后台。凭证不可进入日志、任务参数、回调或对局事件。

- `/api/software/agent/bind`：`code`、`installation_id`、`device_secret` 和 `telemetry`。设备生成 256 位随机凭证，服务端只保存哈希。同一安装与凭证重试可恢复成功响应。
- `/api/software/agent/heartbeat`：保留 v1 心跳兼容；无任务执行能力。
- `/api/software/agent/sync`：v2 同步；上传 `request_id`、`telemetry`、`events` 和可选 `receipt`；返回配置、事件确认、任务确认和最多一项任务。

`telemetry` 必须包含绑定产品 `package_name`、`protocol_version: 2`、`supported_tasks`。只有完成适配和验收的执行器才能出现在 supported_tasks。当前 APK 只声明 `sync_config` 与 `collect_agent_logs`，Device Owner 状态不自动等于这些执行器已实现。

事件结构：`event_id`（设备内唯一且不变）、`category`（operation / diagnostic / game）、`data`。服务端按设备与 event_id 去重，相同 ID 不允许改变内容。每请求最多 50 项、每项最多 8 KB；安卓端每批 20 项。只有 acknowledged_events 内的项目才可从本地删除。

任务结构：`id`、`kind`、`payload`（不可变文件快照等）、`lease`、`lease_until`。回执为 `task_id`、`lease`、`state`（succeeded / failed / unsupported）、`result`。只有匹配设备、当前租约和合法状态才会更新任务结果。过期回执返回 receipt_status，不阻塞设备后续同步，也不会覆盖新尝试。

request_id 在请求失败后保持不变，直到响应及本地状态落盘。服务端可重放同一请求领取的租约。安卓端先持久化执行结果再确认；重试按 task_id 查执行日志，不能重复制造安装或重启副作用。

## 厂商适配位置

`android-agent/app/src/main/java/life/yifun/agent/TaskAdapters.java` 是执行入口；新增执行器前先补对应能力声明、持久化执行日志、故障状态和真机测试。

- `install_apk`：校验 HTTPS 下载、字节数、SHA-256、包名、签名证书、versionCode 和 minSdk；区分用户确认、管理权限安装与真实安装回执。不得把提交安装请求当成安装成功。
- `rollback_apk`：读取人工选择的旧包快照，核实厂商是否支持恢复/降级；不支持时返回 unsupported。禁止自动卸载导致用户数据丢失。
- `restart_app` / `reboot`：须有经过验证的厂商接口或符合条件的设备管理 API，不能用页面设置代替系统权限。
- `sync_content`：下载到暂存位置、校验后原子切换，游戏进行中不得切换当前会话所用内容；权益失效后禁止新下载/开局使用，具体执行由游戏适配。
- 游戏/系统日志：按产品提供的日志目录或 SDK 授权采集；不能用 Agent 自身快照冒充全系统日志。

## 同签名游戏桥接

管理 APK 声明 signature 权限 `life.yifun.agent.permission.GAME_BRIDGE`。游戏需声明 uses-permission 并与管理 APK 使用同一公司签名。不同签名需另接验证接口，不能移除权限保护。

使用显式有序广播指向 `life.yifun.agent/.GameBridgeReceiver`，读取结果码：

- `life.yifun.agent.GET_CONFIG`：200 时 resultData 为当前缓存 JSON；离线配置过期或未绑定返回 403。读取权限不意味着游戏功能已实现，游戏应按 features / expires_at / offline_valid_until 自行实施控制。
- `life.yifun.agent.REPORT_EVENT`：payload 为最多 8 KB 的 JSON，须有稳定 `event_id`（1–95 位字母、数字、点、下划线、冒号或连字符）和 `event`。支持 game.session_started / game.level_scored / game.session_ended。200 表示已写入本地队列，503 表示未接收，游戏须保留并重试。云端目前记录事件与原始数据，不自动计算尚未约定的游戏业务指标。

## Webhook

仅草稿/停用配置不发送。启用的 HTTPS 回调匹配事件时写入事务 outbox，由维护任务发送。每次附：

- X-Yifun-Delivery：固定投递 ID，接收方用于幂等。
- X-Yifun-Timestamp：当前 Unix 秒。
- X-Yifun-Signature：`sha256=` 加 `HMAC-SHA256(secret, timestamp + '.' + 原始请求体)` 十六进制。

接收方须用原始字节验签、校验时间窗并按 delivery ID 去重；仅 2xx 算成功。DNS 解析结果只允许公网 IP，连接固定已验证 IP 且仍用原域名验证 TLS；禁止跳转。最多 6 次尝试，失败重试间隔从 30 秒指数增长，最长 1 小时。

## 后台与调度

员工 GET `/api/software` 获取权限范围内资料；POST `/api/software/action/resource` / `resource-state` / `task` / `task-action` 使用现有员工会话、CSRF 和栏目写权限。资源修改须携带 revision；产品、客户、设备归属不允许静默更换。所有管理操作记入集团审计。

云端 Cron 每分钟从 Worker 直接访问私有容器 `/internal/android-maintenance`；公开 Worker 拒绝所有 /internal/ 路径，内部标记不是公网凭证。维护包含任务租约回收、告警创建与恢复、过期事件清理和回调 outbox。查看 scheduler_last_run 可确认定时任务实际运行；新调度配置传播可能有延迟。

## 已收到的现场基线

安卓板型号 GB-RK3588，芯片 RK3588，系统 Android 12（API 31）。CPU ABI 由管理 APK 实际上报，不仅根据芯片型号推断系统位数。

公司文件命名为 YW_游戏名称_版本号_日期.apk，已提供示例 Yw_Airconveyor_V1.0.0.260406.apk。原始文件名独立保存，不从文件名猜安卓包名、versionCode、签名证书或 APK 内部真实版本；这些值应从真实 APK 读取。还需真实 APK 或实际包名/签名、板卡厂商管理 SDK 和真机验收。
