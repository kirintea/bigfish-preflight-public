# 运行配置

## 一键启动

在项目根目录安装依赖后，运行 `uv run python main_all.py`。启动器使用 `configs/test.yaml`，同时启动绑定本机的 API 和 Vite；默认端口分别为 8091 和 5173。前端代理地址随 API 端口同步设置。任一服务退出时，启动器会停止另一服务。

```powershell
uv run python main_all.py --port 8093 --frontend-port 5174
```

启动器读取根目录 `.env`，但不覆盖已有进程变量。未设置管理凭据时使用本机测试值 `local-npc-lab`；设置后终端仅提示使用环境凭据。此启动方式用于本机开发。

## 单独启动

`main.py` 读取 YAML 和进程环境，不自行加载 `.env`。测试控制接口需要 `configs/test.yaml`，生产配置不注册测试控制与海滩路由。

```powershell
$env:TEST_ADMIN_TOKEN = [guid]::NewGuid().ToString('N')
$env:SIMULATOR_TOKEN = [guid]::NewGuid().ToString('N')
$env:BIGFISH_OTLP_ENABLED = 'false'
uv run python main.py --config configs/test.yaml --host 127.0.0.1 --port 8091
```

另一个终端启动前端。仅在 API 端口变更时调整代理地址：

```powershell
$env:BIGFISH_API = 'http://127.0.0.1:8091'
npm.cmd --prefix webui run dev -- --port 5173
```

也可运行 `uv run python -m tools.dev_server --port 8091`，启动独立离线测试后端。该工具直接构造配置，不读取 YAML 或 `.env`，生成临时管理凭据并打印，默认使用 `runtime/agent-03-local`；`--storage` 可指定其他隔离目录。

## 配置文件

| 文件 | 用途 | 测试控制 | 默认存储 |
| --- | --- | --- | --- |
| `configs/test.yaml` | 离线或真实模型的交互测试 | 开启 | `runtime/test` |
| `configs/dev.yaml` | 开发后端 | 关闭 | `runtime/dev` |
| `configs/prod.yaml` | 生产边界配置，仍默认离线 | 强制关闭 | `runtime/prod` |
| `configs/otel-local.yaml` | 本地观测集成验证 | 以文件配置为准 | 以文件配置为准 |

YAML 支持 `${NAME}` 与 `${NAME:-default}`。未提供默认值的变量必须存在。`AppConfig` 拒绝未知配置字段，并验证单 worker、凭据区分及观测开关之间的约束。生产文件要求两个凭据环境变量存在，但应为其设置非空且不同的值。

## 环境变量

下表描述测试和开发 YAML 中的变量；其他配置是否使用它们取决于文件中的占位符。

| 变量 | 含义 |
| --- | --- |
| `APP_ENV` | `ConfigManager` 未收到配置路径时使用的环境名；显式路径优先 |
| `TEST_ADMIN_TOKEN` | 测试控制、观测查询和指标的 Bearer 凭据 |
| `SIMULATOR_TOKEN` | 模拟来源凭据；仍需配置世界、来源 ID 和领域范围 |
| `BIGFISH_OFFLINE_MODE` | 默认 `true`；`false` 使用配置的真实模型 |
| `LLM_PROVIDER` | 消息 Formatter 选择，默认 `openai` |
| `LLM_API_KEY` | 真实模型凭据 |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 |
| `LLM_MODEL_NAME` | 供应商模型标识 |
| `BIGFISH_OTLP_ENABLED` | 是否向收集器导出；test/dev 默认 `true` |
| `BIGFISH_OTLP_ENDPOINT` | OTLP gRPC 地址，默认 `http://127.0.0.1:4317` |
| `BIGFISH_API` | Vite 使用的后端代理地址 |

`main_all.py --real-agent` 设置离线开关为 `false` 并检查密钥；不带该参数时仅在环境未指定开关时设置为 `true`。所有在线模型均通过 `OpenAIChatModel` 构造，`LLM_PROVIDER` 选择 Formatter，不代表任意供应商原生协议均已集成。

`.env.example` 的主要配置项与本机 `.env` 的结构一致，可选覆盖项以注释列出。`LLM_BASE_URL` 的示例域名必须替换为实际服务地址，`LLM_MODEL_NAME` 必须是该服务支持的标识。仅离线体验时无需填写模型密钥。`APP_ENV` 不覆盖 CLI 指定的路径：`main.py` 默认 `configs/dev.yaml`，`main_all.py` 默认 `configs/test.yaml`。

## 数据与凭据

`storage_dir` 决定业务文件、日志和本地观测目录。文件后端持有存储根写入锁，同一目录不能启动多个写入进程。需要同时运行多个实例时，分别指定端口和存储目录。

`.env`、`runtime/`、日志、依赖缓存和构建输出不纳入版本控制。NPC LAB 凭据仅保留在前端内存中；海滩玩家使用单个隔离测试会话的 cookie。管理视图与角色可见视图不同，不能将管理视图直接传给模型。

## 观测

本机 OTel Collector 与 Jaeger 启动配置位于 [docker/docker-compose.yml](../docker/docker-compose.yml)：

```powershell
docker compose -f docker/docker-compose.yml up -d
```

访问 `http://127.0.0.1:16686`，产生一次 NPC 模型回合后选择服务 `bigfish-agent`。应用通过 `http://127.0.0.1:4317` 向 Collector 上报，与 `.env.example` 一致；Collector 再转发至容器网络内的 `jaeger:4317`。Jaeger 使用 Badger 命名卷保存链路，正常重启和 `down` 不清空；`down -v` 会删除数据。当前仅配置 traces 管线，不采集 OTel metrics/logs。停止命令和端口说明见 [Docker 说明](../docker/README.md)。

每个响应包含 `X-Request-ID`、`X-Trace-ID` 和 `traceparent`。管理身份可查询 `/api/v1/observe/requests/{request_id}`、`/api/v1/observe/status` 与 `/metrics`。

本地阶段缓冲默认保留 4096 条记录，API 查询范围仅为当前进程。`observe/stages.jsonl` 只写错误和拒绝，默认每文件 2 MB，保留两个轮转副本；重启不会将其重放为业务状态。退出诊断为 `observe/shutdown-status.json`。

服务日志位于存储目录的 `logs/` 下，仅写 WARNING 及以上，按日轮转并保留 30 天。模型异常保留脱敏堆栈和 trace 关联，不主动写入密钥、对话正文或请求头。

可选 OTLP 导出使用 AgentScope 推理链路，包含框架采集的模型输入、输出、耗时、异常与可用的用量信息。推理内容会进入所配置的收集器；普通请求和页面轮询不作为推理 span 导出。没有收集器时设置 `BIGFISH_OTLP_ENABLED=false`；这不会关闭本地阶段查询。
