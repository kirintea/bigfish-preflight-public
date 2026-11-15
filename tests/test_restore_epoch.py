import pytest


def test_restore_publishes_new_epoch_and_rejects_old_epoch(tmp_path):
    from core.game.repository import WorldRepository
    from core.saves.service import SaveService
    from core.testing.commands import Command, execute

    repo = WorldRepository(tmp_path / "worlds"); repo.create("test", "world-a", "epoch-a", ["npc-a"])
    service = SaveService(tmp_path / "saves", repo); snapshot = service.create("test", "world-a")
    restored = service.restore("test", "world-a", snapshot.snapshot_id)
    assert restored.run_epoch != "epoch-a"
    with pytest.raises(Exception, match="stale_epoch"):
        execute(repo, "world-a", Command(command_id="old", run_epoch="epoch-a", expected_revision=1), lambda w: {}, operation="old")
