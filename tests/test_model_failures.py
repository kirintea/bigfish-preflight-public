from uuid import uuid4

from core.agent.turns import TurnRequest, TurnService
from core.agent.turns import ModelTurnError


def test_timeout_uses_fallback_and_terminal_status(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="timeout")
    world = service.create_world(["npc-a"])
    result = service.submit(world.world_id, TurnRequest(
        request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
        speaker_id="player", trigger="player_message", text="hello"))
    assert result.status == "fallback"
    assert result.error_code == "model_timeout"


def test_strict_mode_raises_without_fallback_reply(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="timeout")
    world = service.create_world(["npc-a"])
    request = TurnRequest(request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
                          speaker_id="player", trigger="player_message", text="hello",
                          allow_fallback=False)
    try:
        service.submit(world.world_id, request)
    except ModelTurnError as exc:
        assert exc.error_code == "model_timeout"
    else:
        raise AssertionError("strict mode must not return a fallback reply")
