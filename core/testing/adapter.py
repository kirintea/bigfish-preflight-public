from core.reporting.sources import Source


def test_source(world):
    return Source("test", world.test_run_id, "test", frozenset({world.world_id}))
