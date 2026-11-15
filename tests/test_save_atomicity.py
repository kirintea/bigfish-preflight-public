def test_failed_replace_keeps_previous_snapshot(tmp_path, monkeypatch):
    from core.game.repository import WorldRepository
    from core.saves.service import SaveService
    repo = WorldRepository(tmp_path / "worlds"); repo.create("test", "world-a", "epoch-a", ["npc-a"])
    service = SaveService(tmp_path / "saves", repo); first = service.create("test", "world-a")
    monkeypatch.setattr(service, "_replace", lambda *_: (_ for _ in ()).throw(OSError("replace_failed")))
    try:
        service.create("test", "world-a")
    except OSError:
        pass
    else:
        raise AssertionError("replace should fail")
    assert service.read(first.snapshot_id).snapshot_id == first.snapshot_id
