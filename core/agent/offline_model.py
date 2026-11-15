# -*- coding: utf-8 -*-

"""Deterministic offline chat model for acceptance runs.

Implements the AgentScope ``ChatModelBase`` interface so it plugs into the
same generation chain as the real model. The mode is chosen by server-side
test configuration only — player message content can never switch it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agentscope.credential import CredentialBase
from agentscope.message import Msg, TextBlock
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason

from core.config.schemas import OfflineModelMode

VALID_REPLY = {
    "utterance": "聊完我可以带你过去。",
    "recipient_ids": ["player"],
    "reply_to_message_id": None,
    "expression_id": "neutral",
    "intent": None,
    "basis_refs": [],
}

ILLEGAL_INTENT_REPLY = dict(
    VALID_REPLY,
    utterance="跟我来，我带你去个好地方。",
    intent={"candidate_id": "unregistered-takeover", "parameters": {}},
)

WRONG_SPEAKER_REPLY = dict(
    VALID_REPLY,
    utterance="（冒充别人的口吻）",
    speaker="player",
)


class OfflineCredential(CredentialBase):
    """Placeholder credential; the offline model never authenticates."""

    type: str = "offline_credential"

    @classmethod
    def get_chat_model_class(cls):
        return OfflineChatModel


class OfflineChatModel(ChatModelBase):
    """Scripted model returning canned turn output per configured mode."""

    def __init__(
        self,
        mode: OfflineModelMode = "valid_reply",
        model: str = "offline-script",
        npc_id: str = "npc",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            credential=OfflineCredential(),
            model=model,
            parameters=self.Parameters(),
            stream=False,
            max_retries=0,
            retry_delay=0.0,
            context_size=kwargs.pop("context_size", 128000),
        )
        self.mode = mode
        self.npc_id = npc_id

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> ChatResponse:
        if self.mode == "timeout":
            raise TimeoutError("offline model timeout (configured mode)")

        if self.mode == "invalid_json":
            text = "好的，我们这就去海边吧。"  # plain prose, not JSON
        elif self.mode == "wrong_speaker":
            text = json.dumps(WRONG_SPEAKER_REPLY, ensure_ascii=False)
        elif self.mode == "illegal_intent":
            text = json.dumps(ILLEGAL_INTENT_REPLY, ensure_ascii=False)
        else:  # valid_reply
            text = json.dumps(VALID_REPLY, ensure_ascii=False)

        return ChatResponse(
            content=[TextBlock(text=text)],
            is_last=True,
            finished_reason=FinishedReason.COMPLETED,
            metadata={"offline_mode": self.mode},
        )
