from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import HookFragment


@dataclass
class HookSkip:
    hook_id: str
    reason: str


@dataclass
class HookAssembly:
    applied: list[HookFragment] = field(default_factory=list)
    skipped: list[HookSkip] = field(default_factory=list)
    trimmed: list[HookSkip] = field(default_factory=list)
    dependencies: dict = field(default_factory=dict)

    def public_text_for(self, npc_id: str):
        return "\n".join(x.content for x in self.applied if not x.secret and (not x.npc_scope or npc_id in x.npc_scope))

    def prompt_text_for(self, npc_id: str):
        """Return all fragments this NPC is allowed to know, including private hooks."""
        return "\n".join(
            x.content for x in self.applied
            if not x.npc_scope or npc_id in x.npc_scope
        )


class HookAssembler:
    def __init__(self, registry):
        self.registry = registry

    def filter_fragment(self, fragment, *, world_id, npc_id):
        if fragment.secret and (not fragment.npc_scope or npc_id not in fragment.npc_scope):
            return None
        if self.registry.get(fragment.hook_id) is None:
            return None
        return fragment

    def assemble(self, *, world_id, npc_id, tick, event_ids, conversation_mode=None, active_ids=None):
        result = HookAssembly()
        candidates = []
        for item in self.registry.items():
            d = item.definition
            if active_ids is not None and d.hook_id not in active_ids:
                result.skipped.append(HookSkip(d.hook_id, "not_active")); continue
            if d.world_scope and world_id not in d.world_scope:
                result.skipped.append(HookSkip(d.hook_id, "wrong_world")); continue
            if d.npc_scope and npc_id not in d.npc_scope:
                result.skipped.append(HookSkip(d.hook_id, "wrong_npc")); continue
            if d.conversation_modes and conversation_mode not in d.conversation_modes:
                result.skipped.append(HookSkip(d.hook_id, "wrong_mode")); continue
            if d.start_tick is not None and tick < d.start_tick:
                result.skipped.append(HookSkip(d.hook_id, "not_started")); continue
            if d.end_tick is not None and tick > d.end_tick:
                result.skipped.append(HookSkip(d.hook_id, "expired")); continue
            if d.event_ref and d.event_ref not in event_ids:
                result.skipped.append(HookSkip(d.hook_id, "missing_event")); continue
            try:
                fragment = item.provider.provide(d, npc_id=npc_id, world_id=world_id, tick=tick)
                if fragment is None:
                    raise RuntimeError("empty_fragment")
                candidates.append((d, fragment))
            except Exception:
                if d.required:
                    raise RuntimeError("required_hook_failed")
                result.skipped.append(HookSkip(d.hook_id, "provider_failed"))
        selected_groups = set()
        selected_slots = set()
        for d, fragment in sorted(candidates, key=lambda pair: (-pair[0].priority, pair[0].hook_id)):
            if d.slot in selected_slots or (d.exclusive_group and d.exclusive_group in selected_groups):
                result.skipped.append(HookSkip(d.hook_id, "exclusive_conflict")); continue
            selected_groups.add(d.exclusive_group) if d.exclusive_group else None
            if self.filter_fragment(fragment, world_id=world_id, npc_id=npc_id) is not None:
                result.applied.append(fragment)
                selected_slots.add(d.slot)
        result.dependencies = {x.hook_id: x.version for x in result.applied}
        return result
