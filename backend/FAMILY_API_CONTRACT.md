# 家族接口契约

所有家族资料真实写入数据库。GET `/api/family/sync` 返回：

```json
{"family_id": 1, "revision": 0, "role": "OWNER", "profile": {"name": "家族名", "avatar": ""}, "members": [], "reminders": []}
```

PUT `/api/family/sync` 和 POST `/api/family/import` 必须携带 `family_id`、当前 `revision`、`profile`、`members`、`reminders`。服务端保留既有 `client_id` 对应的数据库 ID，增量更新。未出现在新快照中的成员软删除，提醒删除；未修改的数据不重建。写入完成后 revision 加一。

旧版本提交返回 HTTP 409，`detail = {message, remote}`，remote 是当前 SyncOut；前端应三方合并或提示冲突，不得自动覆盖新版本。

成员 `client_id` 与提醒 `client_id` 必须非空且在同一类记录中唯一。成员关联使用 `parent_client_ids`、`spouse_client_id`；提醒关联使用 `member_client_id`。响应也保留数据库关系 ID，便于兼容。后端校验整图、循环和配偶冲突；允许同名成员。

成员 `parent_roles` 与 `parent_client_ids` / `parent_ids` 按位置对应，取值为 `father`、`mother` 或未明确角色的 `parent`。例如仅关联母亲时提交 `parent_client_ids: ["mother-id"]`、`parent_roles: ["mother"]`，无需依赖成员性别。非空角色列表必须与父母数量一致，`father` 和 `mother` 各最多一个；旧数据可省略该字段或使用 `[]`。删除父母成员时同步删除对应角色，关系线仍使用 `kind: parent`。

成员支持 `death_year`（字符串或兼容四位数字）、`death_date`（ISO 日期）。服务端验证完整日期与生卒逻辑。提醒公共字段为 `calendar_type: solar|lunar|qingming`、`lunar_month`、`lunar_day`、`is_leap`；旧字段 `calendar`、`lunar_leap` 可作为输入别名，数据库兼容原命名。advance 输入兼容“提前 7 天”，输出“提前7天”；repeat 为“每年”或“仅一次”。

- GET `/family/list`：数组 `[{id,owner_id,name,avatar,role,revision,active}]`。
- PUT `/family/active` `{family_id}`：返回目标家族 SyncOut。
- POST `/family/invitations` `{invitee,role}`：邀请已注册用户名或手机号；role 是 EDITOR / VIEWER。
- GET `/family/invitations`：OWNER 查看本家族邀请。
- GET `/family/invitations/incoming`：查看发给自己的邀请。
- POST `/family/invitations/{id}/accept`：接受并切换到共享家族，返回 SyncOut。
- POST `/family/invitations/{id}/reject|cancel`：返回 InviteOut。
- InviteOut 为 `{id,family_id,family_name,inviter,invitee,role,status,expires_at}`。
- GET `/family/memberships`：`[{id,user_id,username,role}]`。
- PUT `/family/memberships/{id}` `{role}`、DELETE 同地址：仅 OWNER 可管理；所有者不可降权或移除。
- GET `/family/audit`：`[{id,user_id,username,action,target_type,target_id,created_at}]`。
- GET `/family/export`：返回 SyncOut JSON；导入必须显式使用目标家族和当前版本。

OWNER / EDITOR 可以修改资料，VIEWER 只能读取；OWNER 才能管理邀请与成员资格。直接 profile/member/reminder 写接口也使用同一整图校验、事务、revision 和审计逻辑，`family_id` 与 `revision` 为必填 query 参数。读接口未传 family_id 时读取当前 active 家族。

模型新增 PushSubscription 支持后端 Web Push 的设备订阅；Reminder 同时提供 calendar_type/is_leap ORM 别名。数据库迁移只增列、扩大头像容量、补齐稳定 ID 与所有者成员资格，不删除已有业务记录；迁移可重复执行。

兼容当前管理页面：DELETE `/family/invitations/{id}` 等效 POST `/cancel`，PATCH `/family/memberships/{id}` 等效 PUT；权限校验相同。设备推送模型已补 session_id，密码重置 cutoff 为 User.sessions_valid_after，通知表同时记录 Web Push 和 UniPush 投递状态。
