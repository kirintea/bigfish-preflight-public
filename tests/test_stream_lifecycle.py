import asyncio

import pytest
from agentscope.message import TextBlock
from agentscope.model import ChatResponse
from core.agent.turns import TurnRequest, TurnService


@pytest.mark.asyncio
async def test_real_deltas_arrive_before_completion_and_cancel_rolls_back(tmp_path):
    service = TurnService.for_test(tmp_path)
    world = service.create_world(['npc-a'])
    session = await service.sessions.get_or_create(namespace='test', world_id=world.world_id,
        npc_id='npc-a', conversation_id='c', run_epoch=world.run_epoch)
    seen = asyncio.Event()
    release = asyncio.Event()
    async def chunks():
        yield ChatResponse(content=[TextBlock(text='hello')], is_last=False)
        await release.wait()
        yield ChatResponse(content=[TextBlock(text=' world')], is_last=False)
    async def call(*args, **kwargs):
        return chunks()
    session.agent.model._call_api = call
    received = []
    async def delta(text):
        received.append(text)
        seen.set()
    turn = TurnRequest(request_id='r', conversation_id='c', turn_id='t',
        speaker_id='player', trigger='player_message', text='hello')
    task = asyncio.create_task(service.submit_async(world.world_id, turn, on_delta=delta))
    await asyncio.wait_for(seen.wait(), 2)
    assert received == ['hello'] and not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.state.context == []
    assert service.repository.read('test', world.world_id).agent_states == {}
    assert not service._active

    release.set()
    received.clear()
    result = await service.submit_async(world.world_id, turn, on_delta=delta)
    assert result.utterance == 'hello world'
    assert received == ['hello', ' world']
    assert len(session.state.context) == 2


def test_group_input_does_not_expose_undelivered_history(client):
    from test_group_chat_modes import make_chat
    from api.chat import _chat_inputs
    path, chat = make_chat(client, 'forced')
    world = client.app.state.test_runs.get(path.split('/')[-1])
    def mutate(candidate):
        candidate.chat_sessions[chat['conversation_id']]['messages'].append({
            'message_id': 'secret', 'author': 'player', 'text': 'private token',
            'actual_recipients': ['npc-bigfish'], 'members_at_delivery': ['player', 'npc-bigfish']})
        candidate.revision += 1
        return None, True
    client.app.state.worlds.transact('test', world.world_id, mutate)
    world = client.app.state.worlds.read('test', world.world_id)
    context, _ = _chat_inputs(world, chat['conversation_id'], 'npc-claude')
    assert 'private token' not in context
