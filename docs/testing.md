# 测试与验证

所有命令从项目根目录运行。先执行 `uv sync --group dev` 和 `npm.cmd --prefix webui ci` 安装对应依赖。

## 自动化验证

```powershell
uv run pytest -q -p no:cacheprovider
npm.cmd --prefix webui run build
npm.cmd --prefix webui run test:e2e
```

后端覆盖配置和权限、状态报告与可见性、NPC 回合与失败处理、群聊送达、Hooks、记忆、存档和恢复。前端 build 执行 TypeScript 检查及 Vite 构建；E2E 验证测试台、群聊、海滩交互与不同尺寸布局。

E2E 当前使用 Windows 项目虚拟环境、本机 Chrome 和独立启动的 8092 / 4173 服务，端口应空闲。`BIGFISH_E2E_API_PORT` 可调整 E2E API 端口。数据目录由 `tests/webui_server.py` 创建并清理；截图写入 `runtime/e2e/screenshots/`，失败产物与报告写入 `webui/test-results/` 和 `webui/playwright-report/`。移动尺寸布局通过不代表触屏玩法全部验收。

## CLI 冒烟与汇总

```powershell
uv run python tests/smoke_service.py
uv run python tests/smoke_state.py
uv run python scripts/run_agent_acceptance.py --offline
```

两个冒烟脚本生成临时凭据，启动真实 CLI 并在结束时停止子进程。服务探针写入 `runtime/agent-01-smoke/result.json`；状态探针写入 `runtime/agent-02-smoke/{probe_id}/result.json`，验证秘密隔离、去重与重启持久化。

汇总脚本只运行选定的存档、记忆和会话测试，默认写入 `runtime/acceptance/latest.json`。`--offline` 是结果模式标签；脚本不执行真实模型请求或外部 OTel 验证，也不能替代完整 pytest。

## 外部集成探针

```powershell
uv run --with python-dotenv python tests/probe_integrations.py
uv run --with python-dotenv python tests/probe_integrations.py --llm
```

第一条检查本机 collector / Jaeger，第二条额外产生一次真实模型请求。探针读取本机 `.env` 中的模型配置，不输出凭据或回复，不自动重试模型。`python-dotenv` 为此次运行的临时依赖。供应商实际 token 用量可能与请求上限不同，该参数不能当作可靠费用上限。

外部探针通过只表示所测环境中的连接和链路可用；离线用例通过也不证明真实模型行为、完整游戏执行、长期运行或多机部署可用。

## 产物边界

运行数据、阶段日志、退出诊断、截图和验收 JSON 是本机产物，不随源码分发。阶段日志用于诊断，不是业务重放日志；业务恢复使用世界聚合及存档快照。复现问题时应注明配置文件、离线/真实模型模式、端口和相关 request/trace ID。
