from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class HookDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hook_id: str = Field(min_length=1, max_length=96)
    provider_id: str = Field(min_length=1, max_length=96)
    version: int = Field(ge=1)
    slot: Literal["public_background", "topic", "private_context", "style", "willingness_modifier", "memory_preference"]
    priority: int = 0
    exclusive_group: str | None = None
    world_scope: list[str] | None = None
    npc_scope: list[str] | None = None
    conversation_modes: list[str] | None = None
    time_source: Literal["game_tick"] = "game_tick"
    start_tick: int | None = Field(default=None, ge=0)
    end_tick: int | None = Field(default=None, ge=0)
    required: bool = False
    max_tokens: int = Field(default=512, ge=1)
    event_ref: str | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_tick is not None and self.start_tick is not None and self.end_tick < self.start_tick:
            raise ValueError("invalid_hook_range")
        return self


class HookFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hook_id: str
    provider_id: str
    version: int = Field(ge=1)
    slot: str
    content: str = ""
    npc_scope: list[str] | None = None
    secret: bool = False
    event_ref: str | None = None

    @classmethod
    def from_definition(cls, definition: HookDefinition, content: str, *, secret: bool = False):
        return cls(hook_id=definition.hook_id, provider_id=definition.provider_id, version=definition.version,
                   slot=definition.slot, content=content[:definition.max_tokens * 4],
                   npc_scope=definition.npc_scope, secret=secret, event_ref=definition.event_ref)
