# 家谱 App 后端

## 启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动时会自动连接 `127.0.0.1:3306`，创建 `my_app_zupu` 数据库（如果不存在），并创建或补齐用户、家族、成员、关系、提醒、短信记录和登录日志表。MySQL 用户需要具备创建数据库和表的权限。

新上传的家族头像保存到私有文件目录，数据库保存资源 URL。旧版 `families.avatar` 中的 Base64 图片继续兼容，启动时会将旧 `TEXT` 字段扩容为 `MEDIUMTEXT` 并保留数据。图片上限为 2 MiB。所有响应（包括未处理异常产生的 500）均经过 CORS 中间件。

短信验证码使用环境变量配置阿里云 DYPNS。不要把 AccessKey 写入代码或提交到仓库；可复制 `.env.example` 为本地环境配置。

## 认证接口

注册、登录名/手机号密码登录、手机号短信登录（包括兼容地址 `/api/auth/sms-login`）均必须提交 `accepted_terms_version: "2026-10-14-v1"`。缺失或非当前版本会在密码和短信验证之前返回 422。客户端应先展示完整条款并让用户主动勾选同意；成功认证在会话中记录通过校验的条款版本和服务端 UTC 时间。历史会话的这两个字段保留 NULL，不补写同意；发送短信、找回密码及已登录会话的使用保持原有流程。

- `POST /api/auth/register`：必须提交登录名、密码、手机号及 6 位 `sms_code`；手机号短信登录后的新用户也可提交一次性 `registration_token`
- `POST /api/auth/login`：`{"username":"...","password":"..."}` 或 `{"phone":"<configured-phone>","password":"..."}`
- `POST /api/auth/login/sms`：`{"phone":"<configured-phone>","sms_code":"<code>"}`；已注册手机号直接登录，新手机号返回注册凭证
- `POST /api/auth/send-sms`：`{"phone":"<configured-phone>","scene":"login"}`；注册用 `register`，重置密码用 `reset_password`
- `POST /api/auth/forgot-password`：必须提交 `phone`、`sms_code`、`new_password`
- `GET /api/auth/me`：需要 `Authorization: Bearer <access_token>`

家族业务接口统一位于 `/api/family`，包括资料、成员、关系、提醒、同步、清空、导入导出和邀请记录。

手机号登录使用短信验证码；已注册手机号直接登录，新手机号验证成功后进入注册流程。登录名密码登录和手机号密码登录接口仍保留兼容。

验证码为 6 位数字，有效期 5 分钟；同一手机号 60 秒内不能重发。验证成功后记录仅能用于一次业务操作。短信服务使用阿里云 DYPNS，依赖版本固定为 `alibabacloud-dypnsapi20170525==2.0.0`。开发测试可运行 `PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests -v`，不会触发真实短信。当前配置的阿里云账号若返回发送频率限制，接口会提示“发送太频繁，请稍后再试”；需等待供应商窗口恢复后再进行真机收码验证。

## 实装的账户、图片和通知

登录时创建 `user_sessions`，令牌只保存 SHA-256 指纹。退出登录、撤销设备会话、重置密码会使相应令牌立即失效。旧版 JWT 通过首次认证登记迁移，已撤销令牌不能重新登记。`PATCH /api/auth/preferences` 持久保存通知授权偏好；`DELETE /api/auth/me` 清理其拥有的家族、加入其他家族的资格、邀请、通知、登录及短信验证记录和私有图片文件。

新头像通过 `POST /api/assets` 真正上传 PNG/JPEG/WebP/GIF 图片并保存为服务器文件，最大 2 MiB；数据库保存资源 URL。图片下载需要有效会话，并验证本人或家族成员资格。`ASSET_STORAGE_DIR` 可设置持久化文件目录，部署和备份必须同时保留该目录及数据库。旧版家族头像 dataURL 继续兼容。

API 启动后每 30 秒运行纪念日调度，按 **Asia/Shanghai** 的日期生成提前提醒和当天提醒，并使用数据库唯一键去重。支持公历年度、农历年度、清明节气和仅一次。公历 2 月 29 日在非闰年跳过；农历闰月在该年没有相应闰月时跳过。`GET /api/notifications` 查询收件箱；`PATCH /{id}/read` 和 `POST /read-all` 持久标记已读。关闭网页不会停止服务端生成，后端服务需要持续运行。

`GET /api/notifications/delivery-status` 分别返回收件箱、网页运行时通知、Web Push 和 App 原生后台推送状态。配置 `WEB_PUSH_VAPID_PUBLIC_KEY`、`WEB_PUSH_VAPID_PRIVATE_KEY`、`WEB_PUSH_VAPID_SUBJECT` 后，浏览器可通过 service worker 和 `/api/notifications/subscriptions` 登记设备。服务端调用真实 Web Push 供应商，记录成功、失败和失效订阅；需要 HTTPS（localhost 开发可例外）。未配置时明确显示后台推送未启用；App 原生后台推送需要配置 UniPush 2 及其厂商/APNs 通道，不能将仅保存提醒或浏览器前台通知称为 App 后台推送。

隔离测试运行 `NOTIFICATION_SCHEDULER_ENABLED=false PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v`，使用内存 SQLite、临时图片目录和模拟短信/Web Push 供应商，不发送真实消息。

原生 App 已提供可配置的 UniPush 2/Getui v2 适配：设置 `UNIPUSH_APP_ID`、`UNIPUSH_APP_KEY`、`UNIPUSH_MASTER_SECRET`，App 调用 `uni.getPushClientId` 后登记 `/api/notifications/mobile-devices`。适配器计算真实供应商认证签名并提交单个 CID 推送，厂商/APNs 离线通知需在 DCloud/个推控制台配置。供应商响应 `code=0` 标记为 `mobile_status=ACCEPTED`（接受投递），不能当作设备确认收到；无配置、失败、待登记设备分别明确标注。

Web Push 私钥环境变量支持 32 字节 P-256 raw 私钥的 base64url、DER 的 base64url 或现存 PEM 文件路径；公钥是 65 字节 P-256 UncompressedPoint 的 base64url。服务端实际检查公私钥匹配和 `mailto:`/`https://` 联系地址，仅将公钥返回浏览器。

### 微信小程序订阅提醒

配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`、`WECHAT_REMINDER_TEMPLATE_ID` 和实际模板的 `WECHAT_REMINDER_FIELDS` 映射，例如 `{"thing1":"title","date2":"date","thing3":"family"}`；可用数据源为 title/date/family/body。前端先请求微信订阅授权，再用 `uni.login` code 向 `/notifications/wechat-devices` 登记。服务端通过 code2session 换取 openid，并使用微信订阅消息 API 真正投递。

一次授权按一次投递处理，供应商明确返回 `errcode=0` 才记为 ACCEPTED，不宣称设备已收到；明确拒绝为 FAILED，超时、不完整响应和进程中断等无法确认的请求标记 UNKNOWN，不自动重复投递或扣除授权。设备会话过期、重置密码、撤销设备、退出和注销都会停止对应订阅；移除家族协作者后停止该家族的提醒。没有平台凭证时明确提示未配置；小程序还需自己的 AppID、合法服务域名和模板，不包含任何伪造配置。

前端构建可通过 `VITE_API_BASE_URL=https://服务域名/api` 指定 API 地址；生产 HTTPS 网页应使用 HTTPS API。

## 家族邀请码与登录导览

`POST /api/family/invite-codes?family_id=N` 接受 `{"role":"VIEWER"}` 或 `{"role":"EDITOR"}`，仅该家族所有者可创建、查看列表或撤销。生成 6 位数字码，保留前导零，7 天内单次有效。`GET` 同地址返回最近 100 条记录；`DELETE /api/family/invite-codes/{id}` 撤销未使用的码。每族最多 10 个有效待用码，每管理员每小时最多生成 20 个。

认证用户通过 `POST /api/family/join-by-code` 的 `{"code":"012345"}` 加入；邀请码消费、成员资格、个人谱保留和活跃家谱切换在同一事务提交，返回完整 `SyncOut`。已有成员用码不会升级权限。`POST /api/family/personal` 确保个人家谱存在并切回，不覆盖任何个人或共享资料。错误尝试使用数据库中的独立用户和网络限流桶，15 分钟内分别最多 5 次、30 次；成功退回本次计数。

`GET /api/auth/guides` 返回账号导览偏好及 `show_on_login`；`PUT` 同地址接受 `{"dismissal":"today"}`、`permanent` 或 `reset`。今日关闭按 Asia/Shanghai 日期，永久设置跨设备保留；手动导览入口不受隐藏设置限制。新增 `family_invite_codes`、`invite_code_rate_limits`、`user_guide_settings` 表由正常 API 启动自动创建，注销时清理关联记录。
