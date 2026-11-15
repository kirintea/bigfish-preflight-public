from concurrent.futures import ThreadPoolExecutor

import pytest

from state_helpers import report, system


def test_atomic_replace_failure_does_not_publish_and_retry_reopens(tmp_path, monkeypatch):
    from core.game.repository import WorldRepository
    repo, service, source = system(tmp_path)
    original = repo._replace
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(repo, "_replace", fail)
    data = report()
    assert service.submit(source, data)["reason"] == "storage_error"
    assert repo.read("production", "world-a").revision == 0
    monkeypatch.setattr(repo, "_replace", original)
    assert service.submit(source, data)["status"] == "accepted"
    repo.close()
    reopened = WorldRepository(tmp_path)
    assert reopened.read("production", "world-a").revision == 1
    from core.reporting.service import ReportingService
    assert ReportingService(reopened).submit(source, data)["status"] == "duplicate"
    reopened.close()


def test_concurrent_same_revision_has_single_winner(tmp_path):
    repo, service, source = system(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda data: service.submit(source, data), [report(), report()]))
    assert sorted(r["reason"] for r in results) == ["none", "revision_conflict"]
    assert repo.read("production", "world-a").revision == 1


def test_snapshot_cannot_mutate_repository_and_only_one_writer(tmp_path):
    from core.game.repository import WorldRepository
    repo, _, _ = system(tmp_path)
    snapshot = repo.read("production", "world-a")
    snapshot.revision = 300
    assert repo.read("production", "world-a").revision == 0
    with pytest.raises(RuntimeError, match="writer"):
        WorldRepository(tmp_path)
    repo.close()


def test_batch_result_does_not_expose_mutable_persisted_receipt(tmp_path):
    repo, service, source = system(tmp_path)
    data = report("events", {"events": [{"event_id": "e1", "fact": "rain", "observers": ["npc-a"]}]}, entity_id="world-a")
    batch = dict(batch_id="batch-one", expected_revision=0, reports=[data])
    result = service.submit_batch(source, batch)
    result["event_ids"].append("forged")
    assert service.submit_batch(source, batch)["event_ids"] == ["e1"]
    assert repo.read("production", "world-a").batch_receipts["batch-one"]["event_ids"] == ["e1"]


def test_fsync_failure_preserves_old_disk_version(tmp_path, monkeypatch):
    import os
    from core.game.repository import WorldRepository
    repo, service, source = system(tmp_path)
    with monkeypatch.context() as patch:
        def fail(_):
            raise OSError("fsync failed")
        patch.setattr(os, "fsync", fail)
        assert service.submit(source, report())["reason"] == "storage_error"
    repo.close()
    reopened = WorldRepository(tmp_path)
    assert reopened.read("production", "world-a").revision == 0
    assert not list(tmp_path.rglob("*.tmp"))
    reopened.close()


@pytest.mark.parametrize("world_id", ["../outside", "..\\outside", "C:\\outside", "/root", "a/b", "", ".", "CON"])
def test_world_paths_cannot_escape_storage(tmp_path, world_id):
    from core.game.repository import WorldRepository
    repo = WorldRepository(tmp_path)
    with pytest.raises(ValueError):
        repo.create("production", world_id, "epoch", ["npc-a"])
    repo.close()
