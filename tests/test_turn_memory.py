from uuid import uuid4

from agentscope.state import AgentState

from core.agent.turns import TurnRequest, TurnService
from core.session import persist_key


def test_turns_persist_conversation_context_between_calls(tmp_path):
    service = TurnService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    first = TurnRequest(request_id="r1", conversation_id="c1", turn_id="t1",
                        speaker_id="player", trigger="player_message", text="first question")
    second = TurnRequest(request_id="r2", conversation_id="c1", turn_id="t2",
                         speaker_id="player", trigger="player_message", text="second question")
    service.submit(world.world_id, first)
    service.submit(world.world_id, second)
    persisted = service.repository.read("test", world.world_id).agent_states[
        persist_key(world.world_id, "npc-a", "c1")
    ]
    context = AgentState.model_validate(persisted).context
    texts = [message.get_text_content() for message in context]
    assert "first question" in texts
    assert "second question" in texts
    assert len([text for text in texts if text]) >= 4
