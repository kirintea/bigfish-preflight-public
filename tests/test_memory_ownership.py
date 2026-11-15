import pytest


def test_memory_writer_enforces_world_npc_visibility_and_deduplication():
    from core.memory.writer import MemoryWriter

    world = {"world_id": "w1", "revision": 0, "events": {
        "e1": {"event_id": "e1", "fact": "gold", "observers": ["npc-a"]},
        "secret": {"event_id": "secret", "fact": "hidden", "observers": ["npc-b"]},
    }}
    writer = MemoryWriter()
    entry = writer.write(world, owner_npc_id="npc-a", source_event_ids=["e1"], content="gold found", acquisition="direct")
    assert entry.revision == 1 and entry.owner_npc_id == "npc-a"
    assert writer.write(world, owner_npc_id="npc-a", source_event_ids=["e1"], content="gold found", acquisition="direct").memory_id == entry.memory_id
    with pytest.raises(ValueError, match="source_not_visible"):
        writer.write(world, owner_npc_id="npc-a", source_event_ids=["secret"], content="hidden", acquisition="heard")
    with pytest.raises(ValueError, match="cross_world"):
        writer.write({**world, "world_id": "w2"}, owner_npc_id="npc-a", source_event_ids=["e1"], content="x", acquisition="direct")


def test_draft_is_not_persisted_as_memory():
    from core.memory.writer import MemoryWriter
    world = {"world_id": "w", "revision": 0, "events": {}}
    with pytest.raises(ValueError, match="draft_not_memory"):
        MemoryWriter().write(world, owner_npc_id="npc-a", source_event_ids=[], content="draft", acquisition="draft")
