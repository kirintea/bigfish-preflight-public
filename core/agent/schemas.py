"""Shared schemas for the single-NPC generation path."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.config.schemas import OfflineModelMode
from core.reporting.schemas import Identifier

__all__ = ["OfflineModelMode", "NpcProfile", "IntentCandidate"]


class NpcProfile(BaseModel):
    """Static NPC role configuration loaded from configs/npcs/*.yaml."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    npc_id: Identifier
    name: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=1, max_length=8000)
    fallback_reply: str = Field(min_length=1, max_length=500)
    personality_ref: Identifier | None = None


class IntentCandidate(BaseModel):
    """A registered, constrained intent the NPC may propose."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    candidate_id: Identifier
    capability: str = Field(min_length=1, max_length=64)
    parameters_schema: dict = Field(default_factory=dict)


TurnTrigger = Literal["player_message", "system", "scheduler"]
