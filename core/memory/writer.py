from hashlib import sha256

from .schemas import MemoryEntry


class MemoryWriter:
    def __init__(self):
        self._world_id = None
        self._entries = {}

    def write(self, world, *, owner_npc_id, source_event_ids, content, acquisition,
              certainty=None, occurred_at_tick=None, observed_at_tick=None, protected_by=None):
        world_id = world["world_id"]
        if self._world_id is None:
            self._world_id = world_id
        if world_id != self._world_id:
            raise ValueError("cross_world")
        if acquisition == "draft":
            raise ValueError("draft_not_memory")
        events = world.get("events", {})
        for event_id in source_event_ids:
            event = events.get(event_id)
            if event is None or owner_npc_id not in (event.get("observers") or []) and owner_npc_id not in (event.get("actual_recipients") or []):
                raise ValueError("source_not_visible")
        key = (owner_npc_id, tuple(sorted(source_event_ids)), acquisition, content)
        if key in self._entries:
            return self._entries[key]
        memory_id = "mem-" + sha256("|".join(map(str, key)).encode()).hexdigest()[:16]
        entry = MemoryEntry(memory_id=memory_id, world_id=world_id, owner_npc_id=owner_npc_id,
            content=content, source_event_ids=list(source_event_ids), acquisition=acquisition,
            certainty=certainty or ("unconfirmed" if acquisition == "heard" else "confirmed"),
            occurred_at_tick=occurred_at_tick, observed_at_tick=observed_at_tick,
            protected_by=list(protected_by or []))
        self._entries[key] = entry
        return entry
