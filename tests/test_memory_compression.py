def test_compression_preserves_sources_and_rejects_unknown_references():
    from core.memory.compression import CompressionService
    service = CompressionService()
    candidate = service.build_candidate([
        {"memory_id": "m1", "content": "A found gold", "source_event_ids": ["e1"], "occurred_at_tick": 1, "certainty": "confirmed"},
        {"memory_id": "m2", "content": "A promised return", "source_event_ids": ["e2"], "occurred_at_tick": 2, "certainty": "unconfirmed"},
    ], target_version=2)
    assert candidate.version == 2
    assert candidate.facts and candidate.claims and candidate.source_refs == ["e1", "e2"]
    assert service.validate(candidate, valid_sources={"e1", "e2"}) is True
    assert service.validate(candidate, valid_sources={"e1"}) is False
