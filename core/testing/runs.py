from uuid import uuid4

from core.game.repository import safe_id


class TestRuns:
    def __init__(self, repository):
        self.repository = repository

    def create(self, name, npc_ids=None):
        run_id = uuid4().hex
        return self.repository.create("test", "test-" + run_id, uuid4().hex,
            npc_ids or ["npc-a", "npc-b", "npc-c"], test_run_id=run_id, name=name)

    def get(self, run_id):
        safe_id(run_id)
        world = self.repository.read("test", "test-" + run_id)
        if world.test_run_id != run_id:
            raise KeyError("not_found")
        return world
