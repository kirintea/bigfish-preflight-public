from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import HookDefinition


@dataclass
class RegisteredHook:
    definition: HookDefinition
    provider: Any


class HookRegistry:
    def __init__(self):
        self._items: dict[str, RegisteredHook] = {}

    def register(self, definition: HookDefinition, provider=None):
        if provider is None:
            raise ValueError("provider_not_registered")
        if definition.hook_id in self._items:
            raise ValueError("duplicate_hook")
        self._items[definition.hook_id] = RegisteredHook(definition, provider)

    def items(self):
        return tuple(self._items.values())

    def get(self, hook_id):
        return self._items.get(hook_id)
