import asyncio

from uuid import uuid4

from core.agent.turns import TurnRequest, TurnService


def test_invalid_model_output_returns_fallback_without_committing(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="invalid_json")
    world = service.create_world(["npc-a"])
    request = TurnRequest(
        request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
        speaker_id="player", trigger="player_message", text="hello",
    )
    result = service.submit(world.world_id, request)
    assert result.status == "fallback"
    assert result.utterance
    assert service.repository.read("test", world.world_id).agent_states == {}


def test_valid_model_output_commits_after_validation(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="valid_reply")
    world = service.create_world(["npc-a"])
    request = TurnRequest(
        request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
        speaker_id="player", trigger="player_message", text="hello",
    )
    result = service.submit(world.world_id, request)
    assert result.status == "succeeded"
    assert result.recipient_ids == ["player"]
    assert service.repository.read("test", world.world_id).agent_states


def test_illegal_intent_falls_back(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="illegal_intent")
    world = service.create_world(["npc-a"])
    result = service.submit(world.world_id, TurnRequest(
        request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
        speaker_id="player", trigger="player_message", text="hello"))
    assert result.status == "fallback"
    assert result.error_code == "invalid_model_output"


def test_plain_text_model_reply_is_accepted(tmp_path):
    service = TurnService.for_test(tmp_path, offline_model_mode="valid_reply")
    world = service.create_world(["npc-a"])
    session = asyncio.run(service.sessions.get_or_create(namespace="test", world_id=world.world_id,
        npc_id="npc-a", conversation_id="plain", run_epoch=world.run_epoch))

    class Response:
        content = [type("Text", (), {"type": "text", "text": "你好，我在这里。"})()]

    async def call(*args, **kwargs):
        return Response()

    session.agent.model._call_api = call
    result = service.submit(world.world_id, TurnRequest(
        request_id=uuid4().hex, conversation_id="plain", turn_id="t1",
        speaker_id="player", trigger="player_message", text="hello"))
    assert result.status == "succeeded"
    assert result.utterance == "你好，我在这里。"
