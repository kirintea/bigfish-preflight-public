from uuid import uuid4


def report(domain="body", payload=None, **changes):
    data = dict(schema_version=1, report_id=uuid4().hex, request_id="caller-request",
                world_id="world-a", run_epoch="epoch-a", domain=domain, entity_id="npc-a",
                source_kind="simulation", source_id="sim-a", sequence=1, expected_revision=0,
                mode="snapshot", occurred_at_tick=10, observed_at_tick=10,
                payload=payload if payload is not None else {"present": True, "awake": True, "can_speak": True})
    data.update(changes)
    return data


def system(tmp_path):
    from core.game.repository import WorldRepository
    from core.reporting.service import ReportingService
    from core.reporting.sources import Source
    repository = WorldRepository(tmp_path)
    repository.create("production", "world-a", "epoch-a", ["npc-a", "npc-b", "npc-c"])
    source = Source("simulation", "sim-a", "production", frozenset({"world-a"}))
    return repository, ReportingService(repository), source


def run_report(run, domain="body", payload=None, **changes):
    identity = dict(world_id=run["world_id"], run_epoch=run["run_epoch"],
                    source_kind="test", source_id=run["test_run_id"])
    return report(domain, payload, **(identity | changes))
