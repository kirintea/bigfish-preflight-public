import json

from state_helpers import report, system


def test_secret_is_isolated_across_two_worlds_with_same_npc_ids(tmp_path):
    from core.game.views import npc_context
    repo, service, source = system(tmp_path)
    repo.create("production", "world-b", "epoch-b", ["npc-a", "npc-b", "npc-c"])
    data = report("events", {"events": [{"event_id": "secret-one", "fact": "world-a private treasure", "observers": ["npc-a"]}]}, entity_id="world-a")
    assert service.submit(source, data)["status"] == "accepted"
    for world_id in ("world-a", "world-b"):
        world = repo.read("production", world_id)
        for npc in world.npc_ids:
            serialized = json.dumps(npc_context(world, npc))
            assert ("world-a private treasure" in serialized) == (world_id == "world-a" and npc == "npc-a")
            if world_id == "world-b" or npc != "npc-a":
                assert "secret-one" not in serialized


def test_secret_event_visibility_history_and_no_duplicate_knowledge(tmp_path):
    from core.game.views import npc_context
    repo, service, source = system(tmp_path)
    event = {"event_id": "secret-1", "fact": "hidden gold in cellar", "actor": "npc-b", "targets": ["npc-c"],
             "observers": ["npc-a"], "actual_recipients": [], "source": "direct", "occurred_at_tick": 1}
    data = report("events", {"events": [event]}, entity_id="world-a")
    assert service.submit(source, data)["status"] == "accepted"
    assert service.submit(source, data)["status"] == "duplicate"
    later = report("events", {"events": [{"event_id": "public-2", "fact": "rain", "observers": ["npc-c"]}]},
                   entity_id="world-a", sequence=2, expected_revision=1)
    service.submit(source, later)
    historical = report("events", {"events": [{"event_id": "old-3", "fact": "older news", "observers": ["npc-a"]}]},
                        entity_id="world-a", sequence=3, expected_revision=2, occurred_at_tick=2, observed_at_tick=20)
    assert service.submit(source, historical)["status"] == "accepted"
    world = repo.read("production", "world-a")
    a, b, c = [npc_context(world, npc) for npc in world.npc_ids]
    assert "hidden gold" in json.dumps(a)
    assert "older news" in json.dumps(a)
    assert len(a["knowledge"]) == 2
    assert "hidden gold" not in json.dumps(b) + json.dumps(c)
    assert "secret-1" not in json.dumps(b) + json.dumps(c)


def test_private_domains_resources_and_messages_are_filtered(tmp_path):
    from core.game.views import npc_context
    repo, service, source = system(tmp_path)
    for index, data in enumerate([
        report("needs", {"influences": [{"name": "private grief", "value": 0.3, "source": "personal"}]}),
        report("resources", {"items": [{"item_id": "hidden-cache", "quantity": 2.0, "visible_to": ["npc-a"]}]}, entity_id="world-a"),
        report("conversation", {"members": ["npc-a", "npc-b", "npc-c"], "messages": [
            {"message_id": "m1", "author": "npc-a", "text": "private letter", "targets": ["npc-c"], "actual_recipients": ["npc-b"]}]}, entity_id="chat-a"),
    ]):
        assert service.submit(source, {**data, "expected_revision": index})["status"] == "accepted"
    world = repo.read("production", "world-a")
    c = json.dumps(npc_context(world, "npc-c"))
    assert all(secret not in c for secret in ["private grief", "hidden-cache", "private letter", "m1"])
    assert "private letter" in json.dumps(npc_context(world, "npc-b"))


def test_unknown_fields_are_explicit_and_unknown_npc_is_controlled(tmp_path):
    from core.game.views import npc_context
    repo, _, _ = system(tmp_path)
    world = repo.read("production", "world-a")
    view = npc_context(world, "npc-a")
    assert view["domains"]["body"]["status"] == "unknown"
    assert view["domains"]["hooks"]["status"] == "unsupported"
    assert view["stages"] == {"memory": "skipped", "hooks": "skipped", "model": "skipped"}
    with __import__("pytest").raises(KeyError):
        npc_context(world, "ghost")


def test_event_source_and_opinion_basis_do_not_disclose_unknown_event_ids(tmp_path):
    from core.game.views import npc_context
    repo, service, source = system(tmp_path)
    data = report("events", {"events": [
        {"event_id": "secret-source", "fact": "hidden gold", "observers": ["npc-a"]},
        {"event_id": "heard", "fact": "a rumor", "kind": "hearsay", "source": "hearsay", "source_event_id": "secret-source", "actual_recipients": ["npc-b"]},
    ]}, entity_id="world-a")
    assert service.submit(source, data)["status"] == "accepted"
    assert service.submit(source, report("social", {"opinions": [{"target_id": "npc-a", "value": 0.3, "basis_event_ids": ["secret-source"]}]},
                                        entity_id="npc-b", expected_revision=1))["status"] == "accepted"
    serialized = json.dumps(npc_context(repo.read("production", "world-a"), "npc-b"))
    assert "secret-source" not in serialized
    assert "hidden gold" not in serialized


def test_historical_event_survives_location_disappearance(tmp_path):
    repo, service, source = system(tmp_path)
    assert service.submit(source, report("environment", {"locations": [{"location_id": "old-place", "visible_to": ["npc-a"]}]},
                                        entity_id="world-a"))["status"] == "accepted"
    assert service.submit(source, report("events", {"events": [{"event_id": "past", "fact": "past event", "location_id": "old-place", "observers": ["npc-a"]}]},
                                        entity_id="world-a", expected_revision=1))["status"] == "accepted"
    result = service.submit(source, report("environment", {"locations": []}, entity_id="world-a", sequence=2, expected_revision=2))
    assert result["status"] == "accepted"
    assert repo.read("production", "world-a").events["past"]["location_id"] == "old-place"


def test_member_exit_preserves_delivered_message_history(tmp_path):
    from core.game.views import npc_context
    repo, service, source = system(tmp_path)
    data = report("conversation", {"members": ["npc-a", "npc-b"], "messages": [
        {"message_id": "m1", "author": "npc-a", "text": "delivered earlier", "actual_recipients": ["npc-b"]}]}, entity_id="chat-a")
    assert service.submit(source, data)["status"] == "accepted"
    delta = report("conversation", {"members": ["npc-a"]}, entity_id="chat-a", sequence=2, expected_revision=1, mode="delta")
    assert service.submit(source, delta)["status"] == "accepted"
    world = repo.read("production", "world-a")
    assert "delivered earlier" in json.dumps(npc_context(world, "npc-b"))
