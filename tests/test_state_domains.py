import pytest
from pydantic import ValidationError

from state_helpers import report, system


CASES = [
    ("world", "world-a", {"tick": 10, "speed": 1.0}, {"speed": -1}),
    ("body", "npc-a", {"present": True}, {"present": "true"}),
    ("needs", "npc-a", {"hunger": 0.8, "mood": None}, {"hunger": 1.1}),
    ("social", "npc-a", {"eligible": False, "personality_ref": "quiet-v1"}, {"eligible": 1}),
    ("activity", "npc-a", {"phase": "working", "progress": 0.2}, {"phase": "teleported"}),
    ("environment", "world-a", {"weather": "rain", "temperature_c": 12.0}, {"positions": [{"npc_id": "npc-a", "distance_m": -2}]}),
    ("resources", "world-a", {"items": [{"item_id": "wood", "quantity": 4.0}]}, {"items": [{"item_id": "wood", "quantity": -1}]}),
    ("groups", "world-a", {"groups": [{"group_id": "farmers", "members": ["npc-a"], "phase": "forming"}]}, {"groups": [{"group_id": "g", "phase": "invalid"}]}),
    ("production", "world-a", {"orders": [{"order_id": "o1", "status": "planned"}]}, {"orders": [{"order_id": "o1", "status": "magic"}]}),
    ("events", "world-a", {"events": [{"event_id": "e1", "fact": "rain", "observers": ["npc-a"]}]}, {"events": [{"event_id": "e1", "fact": "rain", "unknown": 1}]}),
    ("conversation", "chat-a", {"members": ["npc-a"], "messages": []}, {"members": ["npc-a"], "status": "magic"}),
    ("hooks", "world-a", {"hook_id": "festival", "enabled": True}, {"hook_id": "h", "enabled": 1}),
    ("action_result", "action-a", {"status": "accepted"}, {"status": "magic"}),
]


@pytest.mark.parametrize("domain,entity,payload,invalid", CASES)
def test_domain_contracts(domain, entity, payload, invalid):
    from core.reporting.schemas import REPORT_ADAPTER
    parsed = REPORT_ADAPTER.validate_python(report(domain, payload, entity_id=entity))
    assert parsed.domain == domain
    with pytest.raises(ValidationError):
        REPORT_ADAPTER.validate_python(report(domain, invalid, entity_id=entity))


@pytest.mark.parametrize("domain,entity,payload,invalid", CASES)
def test_registered_domains_and_support(tmp_path, domain, entity, payload, invalid):
    _, service, source = system(tmp_path)
    result = service.submit(source, report(domain, payload, entity_id=entity))
    assert result["status"] == ("rejected" if domain in {"hooks", "action_result"} else "accepted")
    assert result["reason"] == ("unsupported_domain" if domain in {"hooks", "action_result"} else "none")


def test_pause_reasons_are_independent_and_tick_cannot_advance(tmp_path):
    from core.game.clock import advance, pause, resume
    repo, service, source = system(tmp_path)
    service.submit(source, report("world", {"tick": 10, "pause_reasons": ["manual", "dialogue"]}, entity_id="world-a"))
    world = repo.read("production", "world-a")
    resume(world, "dialogue")
    with pytest.raises(ValueError, match="paused"):
        advance(world, 1)
    assert world.pause_reasons == {"manual"}
    pause(world, "offline")
    resume(world, "manual")
    assert world.pause_reasons == {"offline"}
    resume(world, "offline")
    advance(world, 1)
    assert world.tick == 11
    result = service.submit(source, report("world", {"tick": 11}, entity_id="world-a", sequence=2, expected_revision=1))
    assert result["reason"] == "paused"
