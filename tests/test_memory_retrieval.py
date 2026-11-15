def test_retrieval_filters_private_owner_and_source_then_ranks_terms():
    from core.memory.retrieval import MemoryIndex
    entries = [
        {"memory_id": "a", "world_id": "w", "owner_npc_id": "npc-a", "content": "gold cellar", "access_state": "detail", "valid": True, "source_event_ids": ["e1"], "importance": 0.8},
        {"memory_id": "b", "world_id": "w", "owner_npc_id": "npc-b", "content": "gold cellar", "access_state": "detail", "valid": True, "source_event_ids": ["e1"], "importance": 1.0},
        {"memory_id": "c", "world_id": "w", "owner_npc_id": "npc-a", "content": "old gold", "access_state": "inaccessible", "valid": True, "source_event_ids": ["e1"], "importance": 2.0},
    ]
    result = MemoryIndex(entries).search(world_id="w", npc_id="npc-a", query="gold", valid_sources={"e1"})
    assert [item.memory_id for item in result.items] == ["a"]
    assert result.excluded["owner"] == 1
