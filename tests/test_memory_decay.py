def test_decay_respects_game_tick_and_protection():
    from core.memory.decay import decay_entries, cleanup_entries
    entries = [
        {"memory_id": "normal", "access_state": "detail", "last_access_tick": 1, "protected_by": []},
        {"memory_id": "protected", "access_state": "detail", "last_access_tick": 1, "protected_by": ["active_commitment"]},
    ]
    changed = decay_entries(entries, current_tick=100, summary_after=10, inaccessible_after=20)
    assert changed[0]["access_state"] == "inaccessible"
    assert changed[1]["access_state"] == "detail"
    assert cleanup_entries(changed, referenced_ids={"normal"})[0]["memory_id"] == "protected"
