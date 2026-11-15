def test_save_roundtrip_preserves_full_world_aggregate(tmp_path):
    from core.game.repository import WorldRepository
    from core.saves.service import SaveService

    repo = WorldRepository(tmp_path / "worlds")
    world = repo.create("test", "world-a", "epoch-a", ["npc-a", "npc-b"])
    def mutate(w):
        w.events["e1"] = {"fact": "gold"}
        w.messages["m1"] = {"text": "hi"}
        w.revision += 1
        return None, True
    repo.transact("test", "world-a", mutate)
    service = SaveService(tmp_path / "saves", repo)
    snapshot = service.create("test", "world-a")
    loaded = service.read(snapshot.snapshot_id)
    assert loaded.world["world_id"] == "world-a"
    assert loaded.world["events"]["e1"]["fact"] == "gold"
    assert loaded.checksum == snapshot.checksum


def test_corrupt_snapshot_is_rejected(tmp_path):
    from core.game.repository import WorldRepository
    from core.saves.service import SaveService
    repo = WorldRepository(tmp_path / "worlds"); repo.create("test", "world-a", "epoch-a", ["npc-a"])
    service = SaveService(tmp_path / "saves", repo); snapshot = service.create("test", "world-a")
    path = tmp_path / "saves" / f"{snapshot.snapshot_id}.json"
    path.write_text(path.read_text().replace(snapshot.checksum, "bad"), encoding="utf-8")
    try:
        service.read(snapshot.snapshot_id)
    except ValueError as exc:
        assert str(exc) == "snapshot_checksum_mismatch"
    else:
        raise AssertionError("corrupt snapshot should be rejected")
