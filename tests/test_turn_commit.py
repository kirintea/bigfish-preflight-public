from uuid import uuid4

from core.agent.turns import TurnRequest, TurnService


def test_duplicate_turn_is_idempotent(tmp_path):
    service = TurnService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    request = TurnRequest(request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
                          speaker_id="player", trigger="player_message", text="hello")
    first = service.submit(world.world_id, request)
    second = service.submit(world.world_id, request)
    assert second == first


def test_same_conversation_rejects_concurrent_turn(tmp_path):
    service = TurnService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    service.reserve(world.world_id, "c1", "t1")
    try:
        service.reserve(world.world_id, "c1", "t2")
    except ValueError as exc:
        assert str(exc) == "conversation_busy"
    else:
        raise AssertionError("expected conversation_busy")
