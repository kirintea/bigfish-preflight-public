"""Turns must send the NPC persona (system prompt) and conversation history.

Regression for: preset replies came back as a generic AI assistant with no
memory — ``TurnService`` called ``model._call_api`` with the bare context,
skipping ``Agent._prepare_model_input`` (system prompt + summary) and never
loading ``configs/npcs/*.yaml`` profiles.
"""

import asyncio

from core.agent.profiles import load_system_prompt
from core.agent.turns import TurnRequest, TurnService
from core.hooks.providers import HarvestTestProvider
from core.hooks.registry import HookRegistry


def _capture_calls(tmp_path, conversation_id="c1"):
    """Run two turns against npc-a, returning messages seen per model call."""
    service = TurnService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    captured = []

    async def instrument():
        session = await service.sessions.get_or_create(
            namespace="test", world_id=world.world_id, npc_id="npc-a",
            conversation_id=conversation_id, run_epoch=world.run_epoch,
        )
        original = session.agent.model._call_api

        async def spy(model_name, messages, tools=None, **kwargs):
            captured.append(list(messages))
            return await original(model_name, messages, tools=tools, **kwargs)

        session.agent.model._call_api = spy

    asyncio.run(instrument())
    for index, text in enumerate(("这里是什么地方？", "我前面发了什么？"), start=1):
        result = service.submit(world.world_id, TurnRequest(
            request_id=f"r{index}", conversation_id=conversation_id,
            turn_id=f"t{index}", speaker_id="player",
            trigger="player_message", text=text,
        ))
        assert result.status == "succeeded", result.error_code
    return captured


def test_model_receives_system_prompt_and_history(tmp_path):
    first_call, second_call = _capture_calls(tmp_path)
    assert len(first_call) == 2 and len(second_call) == 4

    # System prompt arrives as the leading system message.
    assert first_call[0].role == "system"
    assert "npc-a" in first_call[0].get_text_content()

    # First call carries the player input; second call replays the whole
    # exchange so the model can answer "what did I say earlier".
    assert [m.role for m in first_call] == ["system", "user"]
    assert [m.role for m in second_call] == ["system", "user", "assistant", "user"]
    texts = [m.get_text_content() for m in second_call]
    assert "这里是什么地方？" in texts
    assert "我前面发了什么？" in texts


def test_load_system_prompt_uses_persona_and_falls_back():
    persona = load_system_prompt("npc-bigfish")
    assert "大肥鱼" in persona
    # Unknown NPC must not break session creation.
    assert load_system_prompt("npc-ghost") == "你是 npc-ghost。"
def test_active_hook_is_injected_into_model_system_prompt(tmp_path):
    registry = HookRegistry()
    registry.register(HarvestTestProvider.definition(), provider=HarvestTestProvider())
    service = TurnService.for_test(tmp_path, hook_registry=registry)
    world = service.create_world(["npc-a"])
    def activate(candidate):
        candidate.events["harvest-1"] = {"event_id": "harvest-1"}
        candidate.hook_instances["harvest-public"] = {
            "hook_id": "harvest-public", "version": 1, "event_id": "harvest-1",
            "npc_ids": ["npc-a"], "enabled": True,
        }
        candidate.revision += 1
        return None, True

    service.repository.transact("test", world.world_id, activate)
    captured = []
    import asyncio

    async def instrument():
        session = await service.sessions.get_or_create(
            namespace="test", world_id=world.world_id, npc_id="npc-a",
            conversation_id="hooks", run_epoch=world.run_epoch,
        )
        original = session.agent.model._call_api

        async def spy(model_name, messages, tools=None, **kwargs):
            captured.append(messages)
            return await original(model_name, messages, tools=tools, **kwargs)

        session.agent.model._call_api = spy

    asyncio.run(instrument())
    result = service.submit(world.world_id, TurnRequest(
        request_id="hook-r1", conversation_id="hooks", turn_id="hook-t1",
        speaker_id="player", trigger="player_message", text="hello",
    ), npc_id="npc-a")
    assert result.status == "succeeded"
    assert "Public harvest background" in captured[0][0].get_text_content()

    def revoke(candidate):
        candidate.hook_instances.clear()
        candidate.revision += 1
        return None, True
    service.repository.transact('test', world.world_id, revoke)
    service.submit(world.world_id, TurnRequest(request_id='hook-r2', conversation_id='hooks',
        turn_id='hook-t2', speaker_id='player', trigger='player_message', text='again'))
    assert all('Public harvest background' not in m.get_text_content() for m in captured[1])
