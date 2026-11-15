"""NPC session cache, epoch keys, confirmed/candidate state.

Cache key includes world/NPC/conversation/epoch; the persistent key is
world/NPC/conversation (epoch handled by the recovery protocol). TTL only
reclaims cache instances; confirmed state lives in the world aggregate's
``agent_states``; candidate AgentState must not overwrite confirmed state
before the reply commits.
"""

import pytest

from core.config.schemas import LLMConfig


def make_repo(tmp_path, world_id, npc_ids=("npc-a",)):
    from core.game.repository import WorldRepository

    repo = WorldRepository(tmp_path / "worlds")
    repo.create("test", world_id, "epoch-1", list(npc_ids))
    return repo


def make_manager(repo, **overrides):
    from core.session import NpcSessionManager

    kwargs = dict(
        llm=LLMConfig(),
        offline_mode=True,
        offline_model_mode="valid_reply",
        ttl_seconds=300,
    )
    kwargs.update(overrides)
    return NpcSessionManager(repo, **kwargs)


async def get(manager, world_id, npc_id, conversation_id, run_epoch="epoch-1"):
    return await manager.get_or_create(
        namespace="test", world_id=world_id, npc_id=npc_id,
        conversation_id=conversation_id, run_epoch=run_epoch,
    )


# ---------------------------------------------------------------------------
# Cache key includes epoch; persistent key does not
# ---------------------------------------------------------------------------


def test_cache_and_persist_keys():
    from core.session import cache_key, persist_key

    assert cache_key("test", "w1", "npc-a", "c1", "e1") != \
        cache_key("test", "w1", "npc-a", "c1", "e2")
    assert cache_key("test", "w1", "npc-a", "c1", "e1") == \
        cache_key("test", "w1", "npc-a", "c1", "e1")
    assert persist_key("w1", "npc-a", "c1") == persist_key("w1", "npc-a", "c1")
    # Persistent key deliberately excludes the epoch.
    assert "e1" not in persist_key("w1", "npc-a", "c1")


@pytest.mark.asyncio
async def test_epoch_change_does_not_reuse_stale_cache(tmp_path):
    repo = make_repo(tmp_path, "w1")
    manager = make_manager(repo)
    first = await get(manager, "w1", "npc-a", "c1", run_epoch="epoch-1")
    # Same coordinates, new epoch (recovery protocol hands a fresh epoch).
    repo.reset("test", "w1", "epoch-2", expected_epoch="epoch-1")
    second = await get(manager, "w1", "npc-a", "c1", run_epoch="epoch-2")
    assert first is not second
    assert first.run_epoch == "epoch-1"
    assert second.run_epoch == "epoch-2"


# ---------------------------------------------------------------------------
# Isolation: same NPC name across worlds / conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_npc_in_different_worlds_does_not_share_state(tmp_path):
    repo = make_repo(tmp_path, "w1")
    repo.create("test", "w2", "epoch-1", ["npc-a"])
    manager = make_manager(repo)

    s1 = await get(manager, "w1", "npc-a", "c1")
    s2 = await get(manager, "w2", "npc-a", "c1")
    assert s1 is not s2

    from agentscope.message import UserMsg
    s1.agent.state.context.append(UserMsg(name="player", content="只给w1的消息"))
    assert s2.agent.state.context == []
    assert s1.agent.state.session_id != s2.agent.state.session_id


@pytest.mark.asyncio
async def test_same_npc_in_different_conversations_does_not_share_state(tmp_path):
    repo = make_repo(tmp_path, "w1")
    manager = make_manager(repo)
    s1 = await get(manager, "w1", "npc-a", "c1")
    s2 = await get(manager, "w1", "npc-a", "c2")
    assert s1 is not s2

    from agentscope.message import AssistantMsg
    s1.agent.state.context.append(AssistantMsg(name="npc-a", content="c1专属"))
    assert s2.agent.state.context == []


@pytest.mark.asyncio
async def test_same_conversation_different_npcs_does_not_share_state(tmp_path):
    repo = make_repo(tmp_path, "w1", npc_ids=("npc-a", "npc-b"))
    manager = make_manager(repo)
    s1 = await get(manager, "w1", "npc-a", "c1")
    s2 = await get(manager, "w1", "npc-b", "c1")
    assert s1.agent.state.session_id != s2.agent.state.session_id
    assert s1.agent.name == "npc-a"
    assert s2.agent.name == "npc-b"


# ---------------------------------------------------------------------------
# Confirmed state in world aggregate; candidate isolated until commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirmed_state_lands_in_world_agent_states(tmp_path):
    from agentscope.message import AssistantMsg
    from core.session import persist_key

    repo = make_repo(tmp_path, "w1")
    manager = make_manager(repo)
    session = await get(manager, "w1", "npc-a", "c1")
    session.agent.state.context.append(AssistantMsg(name="npc-a", content="已确认的话"))
    manager.commit_candidate(
        namespace="test", world_id="w1", npc_id="npc-a",
        conversation_id="c1", candidate=session.agent.state,
    )
    world = repo.read("test", "w1")
    raw = world.agent_states.get(persist_key("w1", "npc-a", "c1"))
    assert raw is not None
    from agentscope.state import AgentState
    restored = AgentState.model_validate(raw)
    assert restored.context[0].get_text_content() == "已确认的话"


@pytest.mark.asyncio
async def test_candidate_does_not_overwrite_confirmed_before_commit(tmp_path):
    from agentscope.message import AssistantMsg
    from core.session import persist_key

    repo = make_repo(tmp_path, "w1")
    manager = make_manager(repo)
    session = await get(manager, "w1", "npc-a", "c1")
    session.agent.state.context.append(AssistantMsg(name="npc-a", content="第一句"))
    manager.commit_candidate(
        namespace="test", world_id="w1", npc_id="npc-a",
        conversation_id="c1", candidate=session.agent.state,
    )
    before = repo.read("test", "w1").agent_states[persist_key("w1", "npc-a", "c1")]

    # Working (candidate) state moves ahead; confirmed must not follow yet.
    session.agent.state.context.append(AssistantMsg(name="npc-a", content="未提交的候选"))
    after = repo.read("test", "w1").agent_states[persist_key("w1", "npc-a", "c1")]
    assert after == before
    assert len(after["context"]) == 1

    manager.commit_candidate(
        namespace="test", world_id="w1", npc_id="npc-a",
        conversation_id="c1", candidate=session.agent.state,
    )
    committed = repo.read("test", "w1").agent_states[persist_key("w1", "npc-a", "c1")]
    assert len(committed["context"]) == 2


@pytest.mark.asyncio
async def test_ttl_evicts_cache_but_reload_restores_confirmed_state(tmp_path):
    from agentscope.message import AssistantMsg
    from core.session import persist_key

    repo = make_repo(tmp_path, "w1")
    clock = {"now": 0.0}
    manager = make_manager(repo, ttl_seconds=100, time_fn=lambda: clock["now"])

    session = await get(manager, "w1", "npc-a", "c1")
    session.agent.state.context.append(AssistantMsg(name="npc-a", content="跨TTL的记忆"))
    manager.commit_candidate(
        namespace="test", world_id="w1", npc_id="npc-a",
        conversation_id="c1", candidate=session.agent.state,
    )

    # Instance TTL only reclaims the cache entry; next access reloads.
    clock["now"] = 101.0
    reloaded = await get(manager, "w1", "npc-a", "c1")
    assert reloaded is not session
    texts = [m.get_text_content() for m in reloaded.agent.state.context]
    assert "跨TTL的记忆" in texts
    # Confirmed store untouched by the eviction itself.
    world = repo.read("test", "w1")
    assert persist_key("w1", "npc-a", "c1") in world.agent_states


@pytest.mark.asyncio
async def test_cache_hit_returns_same_instance_within_ttl(tmp_path):
    repo = make_repo(tmp_path, "w1")
    clock = {"now": 0.0}
    manager = make_manager(repo, ttl_seconds=100, time_fn=lambda: clock["now"])
    first = await get(manager, "w1", "npc-a", "c1")
    clock["now"] = 50.0
    second = await get(manager, "w1", "npc-a", "c1")
    assert first is second
