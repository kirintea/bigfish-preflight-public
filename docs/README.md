# 项目文档

本项目用于验证浏览器游戏与服务端 NPC Agent 的协作：游戏侧确认状态与行动，模型根据角色可见信息生成回复。默认离线运行，真实模型与外部观测服务按需配置。

## 阅读顺序

1. [项目 README](../README.md)：安装、启动和体验入口。
2. [运行配置](configuration.md)：环境变量、启动器、凭据、文件目录及观测。
3. [架构说明](architecture.md)：状态所有权、模块边界、生成提交与存档恢复。
4. [接口与状态契约](contracts/agent-state-v1.md)：报告信封、版本、权限与 API 分类。
5. [测试与验证](testing.md)：本地验证、集成探针及其保证范围。

## 设计文档

- [AI-Agent 接入与能力边界](ai-agent-boundaries.md)：权限、输入输出、执行与一致性要求。
- [NPC-Agent 核心设计](npc-agent-conversation-memory-hooks.md)：群聊、性格发言、记忆与 Hooks。

设计文档包含目标能力与候选方案；当前实现和验证范围以以上运行文档为准。

## AgentScope 文档

[AgentScope 2.0.7 中文文档](agentscope_docs_2.0.7_zh/index.md)包含框架概览、快速开始、组件与部署说明，作为项目所用框架版本的配套资料。

## 当前范围

海滩序章和 NPC LAB 是可运行的原型入口。NPC 生成、群聊、Hooks、记忆和存档已有实现与对应测试，但不代表完整玩法、长期运行容量或生产部署已经验收。

字段级定义以 `core/config/schemas.py`、`core/reporting/schemas.py` 及运行服务的 `/openapi.json` 为准。管理测试接口还提供 `/api/test/v1/runs/schema`，可查询各状态领域的 Schema 与支持状态。
