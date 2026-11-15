# -*- coding: utf-8 -*-

"""NPC 生成工厂：装配模型、消息格式、上下文压缩与观测中间件。

生成 Agent 不持有执行工具；行动由游戏侧能力校验与执行器处理。
上下文摘要保留角色已知事实、待答问题和有效约定。
"""

from __future__ import annotations

from agentscope.agent import Agent, ContextConfig, InjectionConfig, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.formatter import (
    AnthropicChatFormatter,
    DashScopeChatFormatter,
    DeepSeekChatFormatter,
    GeminiChatFormatter,
    MoonshotChatFormatter,
    OllamaChatFormatter,
    OpenAIChatFormatter,
    XAIChatFormatter,
)
from agentscope.middleware import ReplyBudgetControlMiddleware, TracingMiddleware
from agentscope.model import OpenAIChatModel
from agentscope.state import AgentState
from pydantic import SecretStr

from core.config.schemas import LLMConfig, OfflineModelMode
from core.formatter import SiliconFlowFormatter
from middleware.tracing_context import TracingContextMiddleware

from .offline_model import OfflineChatModel

# 摘要仅保留 NPC 对话语义，排除与角色无关的运行细节。
NPC_COMPRESSION_PROMPT = (
    "将以下对话历史压缩为结构化摘要。保留角色已知的关键事实、"
    "尚未回应的问题与仍然有效的约定；使用绝对时间与完整标识；"
    "不要保留与角色无关的运行细节。"
)

NPC_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "key_facts": {
            "type": "string",
            "description": "角色已知的关键事实",
        },
        "open_questions": {
            "type": "string",
            "description": "尚未回应的问题",
        },
        "pending_commitments": {
            "type": "string",
            "description": "仍然有效的约定",
        },
    },
    "required": ["key_facts", "open_questions", "pending_commitments"],
}


class AgentFactory:
    """按世界/NPC 装配生成用 Agent；不授予任何执行类工具。"""

    @staticmethod
    def select_formatter(llm: LLMConfig):
        """按 provider 选择 Formatter；未知 provider 回退 OpenAI。"""
        formatter_map = {
            "anthropic": AnthropicChatFormatter,
            "dashscope": DashScopeChatFormatter,
            "deepseek": DeepSeekChatFormatter,
            "gemini": GeminiChatFormatter,
            "moonshot": MoonshotChatFormatter,
            "ollama": OllamaChatFormatter,
            "openai": OpenAIChatFormatter,
            "siliconflow": SiliconFlowFormatter,
            "xai": XAIChatFormatter,
        }
        return formatter_map.get(llm.provider, OpenAIChatFormatter)()

    @staticmethod
    def create_model(
        llm: LLMConfig,
        *,
        offline_mode: bool,
        offline_model_mode: OfflineModelMode = "valid_reply",
        npc_id: str = "npc",
    ):
        """创建离线脚本模型或真实 OpenAI 兼容模型（构造期不发网络请求）。"""
        if offline_mode:
            return OfflineChatModel(
                mode=offline_model_mode,
                model="offline-script",
                npc_id=npc_id,
                context_size=llm.context_size,
            )
        credential = OpenAICredential(
            api_key=SecretStr(llm.api_key.get_secret_value()),
            base_url=llm.base_url,
        )
        return OpenAIChatModel(
            credential=credential,
            model=llm.model,
            stream=llm.stream,
            context_size=llm.context_size,
            formatter=AgentFactory.select_formatter(llm),
            parameters=OpenAIChatModel.Parameters(
                max_tokens=llm.max_tokens,
                temperature=llm.temperature,
            ),
        )

    @staticmethod
    def create(
        *,
        npc_id: str,
        system_prompt: str,
        llm: LLMConfig,
        offline_mode: bool = True,
        offline_model_mode: OfflineModelMode = "valid_reply",
        state: AgentState | None = None,
        otel_enabled: bool = False,
        token_budget: float = 80000,
        max_iters: int = 8,
    ) -> Agent:
        """装配生成 Agent：模型 + Formatter + tracing + 回复预算。

        不授予 Shell、文件、MCP 或工作区访问能力。
        """
        model = AgentFactory.create_model(
            llm,
            offline_mode=offline_mode,
            offline_model_mode=offline_model_mode,
            npc_id=npc_id,
        )

        middlewares = []
        if otel_enabled:
            middlewares.append(TracingMiddleware())
        middlewares.append(TracingContextMiddleware())
        middlewares.append(ReplyBudgetControlMiddleware(token_budget=token_budget))

        agent = Agent(
            name=npc_id,
            system_prompt=system_prompt,
            model=model,
            toolkit=None,  # 生成阶段无工具；受限行动走游戏侧执行器
            middlewares=middlewares,
            state=state,
            context_config=ContextConfig(
                compression_prompt=NPC_COMPRESSION_PROMPT,
                summary_schema=NPC_SUMMARY_SCHEMA,
            ),
            react_config=ReActConfig(max_iters=max_iters, stop_on_reject=False),
            injection_config=InjectionConfig(),
        )
        agent.__tracing_context__ = {"bigfish.npc.id": npc_id}
        return agent
