def test_restore_keeps_event_memory_hook_and_conversation_references(tmp_path):
    from core.game.repository import WorldRepository
    from core.saves.service import SaveService
    repo = WorldRepository(tmp_path / "worlds"); repo.create("test", "world-a", "epoch-a", ["npc-a"])
    def mutate(w):
        w.events["e"] = {"fact": "x"}
        w.npc_memories["npc-a"] = [{"memory_id": "m"}]
        w.hook_instances["h"] = {"event_id": "e"}
        w.npc_conversations["c"] = {"conversation_id": "c"}
        w.revision += 1
        return None, True
    repo.transact("test", "world-a", mutate)
    service = SaveService(tmp_path / "saves", repo); snap = service.create("test", "world-a"); restored = service.restore("test", "world-a", snap.snapshot_id)
    assert restored.events["e"]["fact"] == "x"
    assert restored.npc_memories["npc-a"][0]["memory_id"] == "m"
    assert restored.hook_instances["h"]["event_id"] == "e"
    assert "c" in restored.npc_conversations
