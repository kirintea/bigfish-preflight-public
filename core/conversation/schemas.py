from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


Mode = Literal["player_formal", "npc_autonomous"]


@dataclass
class Candidate:
    npc_id: str
    eligible: bool
    reason: str


@dataclass
class Opportunity:
    opportunity_id: str
    trigger: str
    conversation_id: str
    selected_npc_id: str | None
    candidates: list[Candidate]
    rules: dict = field(default_factory=dict)
    random_value: float = 0.0


@dataclass
class ConversationMessage:
    message_id: str
    author_id: str
    recipient_ids: list[str]
    actual_recipient_ids: list[str]
    content: str
    sequence: int
    tick: int = 0
    reply_to_message_id: str | None = None
    intent_ref: str | None = None


@dataclass
class Conversation:
    conversation_id: str
    world_id: str
    run_epoch: str
    mode: Mode
    members: list[str]
    member_revision: int = 1
    topic: str | None = None
    turn_sequence: int = 0
    message_sequence: int = 0
    status: Literal["open", "paused", "closed"] = "open"
    end_reason: str | None = None
    messages: list[ConversationMessage] = field(default_factory=list)
    knowledge: dict[str, list[str]] = field(default_factory=dict)
    opportunities: dict[str, Opportunity] = field(default_factory=dict)
    pause_reasons: set[str] = field(default_factory=set)

    @classmethod
    def create(cls, world_id, run_epoch, members, *, mode="npc_autonomous", topic=None):
        members = list(members)
        if len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("invalid_members")
        if mode == "npc_autonomous" and "player" in members:
            raise ValueError("player_not_allowed")
        return cls(uuid4().hex, world_id, run_epoch, mode, members, topic=topic,
                   knowledge={member: [] for member in members})
