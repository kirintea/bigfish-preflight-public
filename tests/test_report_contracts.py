import pytest
from pydantic import ValidationError

from state_helpers import report, system


@pytest.mark.parametrize("changes", [
    {"mode": "replace"}, {"sequence": 0}, {"extra": True}, {"schema_version": 2},
    {"occurred_at_tick": 11}, {"observed_at_tick": -1}, {"world_id": "../escape"},
    {"source_kind": "admin"}, {"expected_revision": -1}, {"sequence": True},
    {"schema_version": True},
    {"payload": {"present": True, "extra": 1}}, {"payload": {"awake": "yes"}},
])
def test_envelope_rejects_invalid_values(changes):
    from core.reporting.schemas import REPORT_ADAPTER
    with pytest.raises(ValidationError):
        REPORT_ADAPTER.validate_python(report(**changes))


def test_sources_are_bound_and_references_checked(tmp_path):
    _, service, source = system(tmp_path)
    assert service.submit(source, report(source_id="pretend"))["reason"] == "forbidden_source"
    assert service.submit(source, report(entity_id="unknown"))["reason"] == "invalid_payload"
    assert service.submit(source, report("social", {"opinions": [{"target_id": "ghost", "value": 0.4}]}))["reason"] == "invalid_payload"


def test_unknown_source_world_and_domain_are_forbidden(tmp_path):
    from core.reporting.sources import Source
    _, service, _ = system(tmp_path)
    source = Source("simulation", "sim-a", "production", frozenset({"other"}))
    assert service.submit(source, report())["reason"] == "forbidden_source"
    source = Source("simulation", "sim-a", "production", frozenset({"world-a"}), frozenset({"needs"}))
    assert service.submit(source, report())["reason"] == "forbidden_source"


def test_hearsay_cannot_be_promoted_to_confirmed_fact(tmp_path):
    _, service, source = system(tmp_path)
    data = report("events", {"events": [{"event_id": "rumor", "fact": "claim", "source": "hearsay",
                                         "kind": "confirmed", "observers": ["npc-a"]}]}, entity_id="world-a")
    assert service.submit(source, data)["reason"] == "invalid_payload"
