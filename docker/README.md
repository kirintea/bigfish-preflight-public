# 本地链路观测 / Local Trace Observation

从项目根目录执行，需要已启动 Docker Engine 和 Docker Compose。
Run from the project root with Docker Engine and Docker Compose running.

```powershell
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

数据流：应用 -> OTel Collector -> Jaeger（Badger 持久化）-> 查询界面。Collector 的接收与转发配置位于 [otel-collector.yaml](otel-collector.yaml)。
Data flow: application -> OTel Collector -> Jaeger (persistent Badger storage) -> query UI. Collector receivers and forwarding are configured in [otel-collector.yaml](otel-collector.yaml).

| 地址 / Address | 用途 / Purpose |
| --- | --- |
| `http://127.0.0.1:16686` | Jaeger 查询界面 / Jaeger query UI |
| `http://127.0.0.1:4317` | Collector OTLP gRPC，应用上报入口 / Collector OTLP gRPC, application export endpoint |
| `http://127.0.0.1:4318` | Collector OTLP HTTP / Collector OTLP HTTP |

应用 `.env` 设置 `BIGFISH_OTLP_ENDPOINT=http://127.0.0.1:4317`。test/dev YAML 默认启用导出；若已有 `BIGFISH_OTLP_ENABLED=false`，需改为 `true` 后重启后端。
Set `BIGFISH_OTLP_ENDPOINT=http://127.0.0.1:4317` in the application's `.env`. The test/dev YAML enables export by default; if `BIGFISH_OTLP_ENABLED=false` is already set, change it to `true` and restart the backend.

执行一次 NPC 模型回合后，在 Jaeger 中选择 `bigfish-agent` 查询。普通健康检查和状态轮询不会产生推理链路。项目当前只向此服务导出 traces，不通过此 Compose 收集 metrics 或 logs。
After an NPC model turn, select `bigfish-agent` in Jaeger. Health checks and state polling do not produce inference traces. This project exports traces to this service; this Compose setup does not collect metrics or logs.

```powershell
docker compose -f docker/docker-compose.yml logs --tail 100 otel-collector jaeger
docker compose -f docker/docker-compose.yml down
```

此配置仅用于本机开发，端口绑定回环地址。Jaeger 的 Badger 数据保存在项目命名卷 `bigfish-otel_jaeger-badger`，正常重启和 `down` 后保留；`down -v` 会删除数据卷及其历史链路。链路保留期限沿用镜像默认设置，需按使用情况管理磁盘容量。
This setup is for local development and binds ports to loopback. Jaeger stores Badger data in the project volume `bigfish-otel_jaeger-badger`, which survives normal restarts and `down`; `down -v` deletes the volume and its trace history. Trace retention follows the image defaults; manage disk usage as needed.

已有服务占用相同端口时，先在此 Compose 中调整映射左侧的主机端口，并同步修改应用 endpoint。容器内 Collector 始终转发至 `jaeger:4317`。项目使用独立服务名和数据卷，不接管其他 Compose 项目的服务或数据。
If existing services use the same ports, change the host ports on the left side of the mappings and update the application endpoint. Inside the network, the Collector always forwards to `jaeger:4317`. This project uses its own service names and data volume and does not take over services or data from other Compose projects.

这些服务不通过环境变量或挂载接收项目的模型密钥。运行配置见[项目配置文档](../docs/configuration.md)。
These services do not receive the application's model credentials through environment variables or mounts. See the [application configuration](../docs/configuration.md).
