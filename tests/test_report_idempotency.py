from state_helpers import report, system


def test_retry_precedes_revision_and_duplicate_has_original_receipt(tmp_path):
    repo, service, source = system(tmp_path)
    data = report()
    first = service.submit(source, data)
    assert first["status"] == "accepted"
    second = service.submit(source, data)
    assert second["status"] == "duplicate"
    assert second["revision"] == first["revision"] == 1
    assert second["event_ids"] == first["event_ids"]
    assert repo.read("production", "world-a").revision == 1
    assert service.submit(source, {**data, "payload": {"present": False}})["reason"] == "id_collision"


def test_epoch_sequence_revision_and_missing_baseline(tmp_path):
    _, service, source = system(tmp_path)
    assert service.submit(source, report(run_epoch="old"))["reason"] == "stale_epoch"
    assert service.submit(source, report(sequence=2))["reason"] == "sequence_gap"
    assert service.submit(source, report(mode="delta"))["reason"] == "missing_baseline"
    assert service.submit(source, report())["status"] == "accepted"
    assert service.submit(source, report(expected_revision=0, sequence=2))["reason"] == "revision_conflict"
    assert service.submit(source, report(expected_revision=1, sequence=1))["reason"] == "sequence_gap"
    assert service.submit(source, report(expected_revision=1, sequence=2, occurred_at_tick=9, observed_at_tick=9))["reason"] == "invalid_payload"
    assert service.submit(source, report(expected_revision=1, sequence=2, mode="delta", payload={"awake": False}))["status"] == "accepted"


def test_batch_uses_single_revision_and_is_all_or_nothing(tmp_path):
    repo, service, source = system(tmp_path)
    a, b = report(), report("needs", {"hunger": 0.8})
    batch = dict(batch_id="batch-a", expected_revision=0, reports=[a, {**b, "entity_id": "ghost"}])
    assert service.submit_batch(source, batch)["reason"] == "invalid_payload"
    assert repo.read("production", "world-a").revision == 0
    batch["reports"][1] = b
    result = service.submit_batch(source, batch)
    assert result["revision"] == 1
    assert service.submit_batch(source, batch)["status"] == "duplicate"
    assert len(repo.read("production", "world-a").report_receipts) == 2
    assert service.submit_batch(source, {**batch, "reports": [a]})["reason"] == "id_collision"


def test_batch_mixed_duplicate_and_new_report_never_partially_commits(tmp_path):
    repo, service, source = system(tmp_path)
    old = report()
    service.submit(source, old)
    result = service.submit_batch(source, dict(batch_id="new-batch", expected_revision=1,
        reports=[{**old, "expected_revision": 1}, report("needs", {"hunger": 0.5}, expected_revision=1)]))
    assert result["status"] != "accepted"
    assert repo.read("production", "world-a").revision == 1


def test_event_ids_deduplicate_across_reports_and_conflicts_do_not_commit(tmp_path):
    repo, service, source = system(tmp_path)
    event = {"event_id": "e1", "fact": "rain", "observers": ["npc-a"]}
    a = report("events", {"events": [event]}, entity_id="world-a")
    assert service.submit(source, a)["status"] == "accepted"
    b = report("events", {"events": [event]}, entity_id="world-a", sequence=2, expected_revision=1)
    assert service.submit(source, b)["status"] == "accepted"
    world = repo.read("production", "world-a")
    assert len(world.events) == len(world.knowledge["npc-a"]) == 1
    bad = report("events", {"events": [{**event, "fact": "snow"}]}, entity_id="world-a", sequence=3, expected_revision=2)
    assert service.submit(source, bad)["reason"] == "id_collision"
    assert repo.read("production", "world-a").revision == 2


def test_delta_fingerprint_distinguishes_omission_from_explicit_null(tmp_path):
    _, service, source = system(tmp_path)
    service.submit(source, report())
    delta = report(payload={"awake": False}, mode="delta", sequence=2, expected_revision=1)
    assert service.submit(source, delta)["status"] == "accepted"
    changed = {**delta, "payload": {"awake": False, "present": None}}
    assert service.submit(source, changed)["reason"] == "id_collision"
