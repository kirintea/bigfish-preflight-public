# 接口与状态契约 v1

精确请求字段以 `core/reporting/schemas.py` 和运行服务的 `/openapi.json` 为准。本说明区分状态报告、测试控制和玩家会话，避免把调试能力视为正式模拟接口。

## 身份与路由

| 路由 | 身份与用途 |
| --- | --- |
| `/health`、`/docs`、`/openapi.json` | 服务健康与接口定义 |
| `/api/v1/worlds/{world_id}/...` | 模拟身份；服务端绑定世界、来源和领域许可 |
| `/api/v1/observe/...`、`/metrics` | 管理身份；查询诊断与指标 |
| `/api/test/v1/runs/...` | 管理身份；隔离测试世界与 Agent 调试 |
| `/api/play/v1/...` | 隔离玩家会话 cookie；海滩玩法入口 |

管理和模拟身份使用不同的 `Authorization: Bearer ...` 凭据。自报 viewer、来源 ID 或角色名称不会增加权限。测试和玩家路由仅在启用测试控制且非生产时注册。

## 报告信封

向 `POST /api/v1/worlds/{world_id}/reports` 或测试 run 的 `/reports` 提交完整报告。例如，已有 `npc-a` 的世界在 revision 0、epoch 为 `epoch-a` 时：

```json
{
  "schema_version": 1,
  "report_id": "report-needs-1",
  "request_id": "caller-1",
  "world_id": "world-a",
  "run_epoch": "epoch-a",
  "domain": "needs",
  "entity_id": "npc-a",
  "source_kind": "simulation",
  "source_id": "sim-a",
  "sequence": 1,
  "expected_revision": 0,
  "mode": "snapshot",
  "occurred_at_tick": 10,
  "observed_at_tick": 10,
  "payload": {"hunger": 0.8, "fatigue": 0.6, "mood": null}
}
```

世界、NPC、来源许可和基线版本必须已存在且匹配。测试适配器有独立来源绑定，不能直接把上述模拟来源当作测试来源。测试世界当前状态通过 `/api/test/v1/runs/{test_run_id}/state` 查询；领域定义使用公共的管理接口 `/api/test/v1/runs/schema` 查询。

`snapshot` 替换对应领域实体载荷，省略的可空字段成为 unknown；`delta` 只修改显式提供的顶层字段，省略保留原值，显式 null 清空。嵌套对象和数组整体替换，delta 必须有基线。世界时钟的省略或 null 不清除已确认 tick 与暂停集合，解除暂停需显式提供新集合。

tick 为非负模拟时间；`occurred_at_tick` 表示发生，`observed_at_tick` 表示观察。它们不等于真实超时使用的单调时钟。当前状态不允许被更早的发生时间覆盖；合法晚到事件可保留历史时间。

## 领域和可见性

| 领域 | 含义 | 角色可读范围 |
| --- | --- | --- |
| `world` | tick、速度、场景、暂停原因 | 公共世界信息 |
| `body`、`needs` | 身体状态、需求与影响 | 本人 |
| `social`、`activity` | 关系、资格、活动与进度 | 本人 |
| `environment` | 天气、位置与地点 | 天气公共，空间项显式过滤 |
| `resources` | 库存、所有者、持有者和预约 | 显式 `visible_to` |
| `groups`、`production` | 群体、生产订单、设施与作物 | 显式 `visible_to` |
| `events` | 不可变事实或传闻及来源 | 实际观察或接收者 |
| `conversation` | 成员与不可变消息 | 作者与实际接收者 |
| `hooks`、`action_result` | 已登记的报告 Schema | 通用报告入口目前不支持写入 |

Hooks 和行动有独立测试 API，其存在不改变报告注册表中 `supported=false` 的边界。字段单位包括距离米、温度摄氏度、需求与进度 0..1、关系意见 -1..1；具体范围与枚举以 Schema 为准。

NPC、地点、任务目标、关系依据事件等引用须有效；同一批次允许共同引入地点和引用。事件的 actor/targets 不自动获得知识，只有 observers/actual_recipients 获得对应索引。消息保留送达时成员快照；成员变化不会改写旧消息的接收范围。

## 幂等、批次与回执

`run_epoch` 拒绝恢复前的旧写入，`expected_revision` 防止基线冲突，来源 `sequence` 防止缺失和乱序。同一 report ID 原样重试返回 duplicate，异内容复用返回冲突；省略字段和显式 null 属于不同内容。

`POST .../reports/batch` 接收 `batch_id`、`expected_revision` 和 1..100 个报告。世界、代次、基线版本与绑定来源须一致；整个批次只增加一次 revision，任一验证或持久化失败均不提交。不同 HTTP 请求之间没有原子批次保证。

```json
{
  "status": "accepted",
  "reason": "none",
  "report_id": "report-needs-1",
  "request_id": "server-request-id",
  "trace_id": "32-hex-trace-id",
  "revision": 1,
  "event_ids": [],
  "errors": []
}
```

`status` 为 accepted、rejected、duplicate、conflict 或 expired。accepted 仅表示报告提交，不能视作行动成功。服务端 request/trace ID 与响应头关联，不直接信任信封中的调用方 ID。重复提交保留原 revision 和事件 ID，但返回本次请求关联。

| HTTP | 常见原因 |
| --- | --- |
| 200 | accepted 或 duplicate，检查 status |
| 401 / 403 | 未认证或不在来源许可范围 |
| 404 | 授权范围内的对象不可用 |
| 409 | revision_conflict、sequence_gap、id_collision、stale_epoch、missing_baseline、paused |
| 422 | invalid_payload 或 unsupported_domain |
| 503 | storage_error，未确认提交，可重试原报告 |

Schema 错误只返回字段路径，不回显原始载荷。正式来源读取 NPC 上下文使用 `GET .../npcs/{npc_id}/context`，返回角色可见状态和请求关联；该读取不触发模型生成。

## 测试与玩家接口

先向 `POST /api/test/v1/runs` 提交 `{"name":"baseline"}` 创建测试世界。返回 `test_run_id`、`world_id`、`run_epoch` 与 revision。该前缀内包含状态报告、场景导入导出/重放、群聊成员与消息、NPC 回合、Hooks、记忆、行动和存档接口。

测试台状态变更常使用 `command_id`、`run_epoch` 和 `expected_revision` 命令信封。重置和预设载入会换代次；收到冲突后先刷新状态。不同 API 的请求模型并不相同，不应把命令信封直接套用于所有管理接口。

模型回合支持普通和 SSE 流式接口；流式事件包含 `delta`、`result` 或 `error`。客户端以最终回执判断成功，文本增量不代表世界提交。NPC 互动和发言机会仍受会话成员、状态及互动模式限制。

玩家通过 `POST /api/play/v1/sessions` 创建隔离海滩，再以会话 cookie 访问 `/state`、`/command` 和 `/reset`。cookie 为 HttpOnly、SameSite=Strict，有效期 8 小时；玩家不能伪造 NPC 作者、确认位置或库存结果。该身份不授予测试管理权限。
