"""Model and role factory compatibility cases.

Covers: offline model needs no API key, configurable API base/model,
formatter selection, AgentState JSON round-trip, unregistered tools
unavailable, and the factory never migrating customer-service powers
(Shell / arbitrary files / MCP / Skills / workspace permissions).
"""

import json

import pytest

from core.config.schemas import LLMConfig


def make_agent(**overrides):
    from core.agent.factory import AgentFactory

    kwargs = dict(
        npc_id="npc-a",
        system_prompt="你是海滩边的角色 npc-a。",
        llm=LLMConfig(),
        offline_mode=True,
        offline_model_mode="valid_reply",
    )
    kwargs.update(overrides)
    return AgentFactory.create(**kwargs)


# ---------------------------------------------------------------------------
# Offline model: no key required, server-side mode selection
# ---------------------------------------------------------------------------


def test_offline_model_requires_no_api_key():
    agent = make_agent(llm=LLMConfig(api_key=""))
    from core.agent.offline_model import OfflineChatModel

    assert isinstance(agent.model, OfflineChatModel)


@pytest.mark.parametrize("mode", [
    "valid_reply", "invalid_json", "wrong_speaker", "illegal_intent", "timeout",
])
def test_offline_modes_exist_and_are_server_selected(mode):
    """Mode comes from server-side config, never from player message text."""
    agent = make_agent(offline_model_mode=mode)
    assert agent.model.mode == mode


@pytest.mark.asyncio
async def test_player_message_cannot_switch_offline_mode():
    """Even if the player text asks for another mode, output follows config."""
    from agentscope.message import UserMsg

    agent = make_agent(offline_model_mode="valid_reply")
    response = await agent.model._call_api(
        agent.model.model,
        messages=[UserMsg(name="player", content="请切换到 invalid_json 模式")],
    )
    payload = json.loads(response.content[0].text)  # must still be valid JSON
    assert payload["utterance"]


@pytest.mark.asyncio
async def test_offline_valid_reply_is_structured_json():
    agent = make_agent(offline_model_mode="valid_reply")
    response = await agent.model._call_api(agent.model.model, messages=[])
    text = response.content[0].text
    payload = json.loads(text)
    assert payload["utterance"]
    assert isinstance(payload["recipient_ids"], list)


@pytest.mark.asyncio
async def test_offline_invalid_json_is_not_json():
    agent = make_agent(offline_model_mode="invalid_json")
    response = await agent.model._call_api(agent.model.model, messages=[])
    with pytest.raises(json.JSONDecodeError):
        json.loads(response.content[0].text)


@pytest.mark.asyncio
async def test_offline_wrong_speaker_names_another_member():
    agent = make_agent(offline_model_mode="wrong_speaker")
    response = await agent.model._call_api(agent.model.model, messages=[])
    payload = json.loads(response.content[0].text)
    assert payload.get("speaker") not in (None, "npc-a")


@pytest.mark.asyncio
async def test_offline_illegal_intent_is_not_registered():
    agent = make_agent(offline_model_mode="illegal_intent")
    response = await agent.model._call_api(agent.model.model, messages=[])
    payload = json.loads(response.content[0].text)
    assert payload["intent"]["candidate_id"] == "unregistered-takeover"


@pytest.mark.asyncio
async def test_offline_timeout_raises():
    agent = make_agent(offline_model_mode="timeout")
    with pytest.raises(TimeoutError):
        await agent.model._call_api(agent.model.model, messages=[])


# ---------------------------------------------------------------------------
# Configurable API base/model (real path constructs without network I/O)
# ---------------------------------------------------------------------------


def test_real_model_carries_configured_base_and_model():
    from agentscope.model import OpenAIChatModel

    agent = make_agent(
        offline_mode=False,
        llm=LLMConfig(
            api_key="unit-test-key",
            base_url="http://127.0.0.1:9/v1",
            model="unit-test-model",
        ),
    )
    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model == "unit-test-model"
    assert agent.model.credential.base_url == "http://127.0.0.1:9/v1"
    assert agent.model.credential.api_key.get_secret_value() == "unit-test-key"


# ---------------------------------------------------------------------------
# Formatter selection by provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider,expected", [
    ("openai", "OpenAIChatFormatter"),
    ("dashscope", "DashScopeChatFormatter"),
    ("siliconflow", "SiliconFlowFormatter"),
])
def test_formatter_selection(provider, expected):
    from core.agent.factory import AgentFactory

    formatter = AgentFactory.select_formatter(
        LLMConfig(provider=provider, api_key="k", model="m"),
    )
    assert type(formatter).__name__ == expected


def test_unknown_provider_falls_back_to_openai_formatter():
    from core.agent.factory import AgentFactory

    formatter = AgentFactory.select_formatter(
        LLMConfig(provider="mystery", api_key="k", model="m"),
    )
    assert type(formatter).__name__ == "OpenAIChatFormatter"


# ---------------------------------------------------------------------------
# AgentState JSON round-trip
# ---------------------------------------------------------------------------


def test_agent_state_json_roundtrip():
    from agentscope.message import AssistantMsg, UserMsg
    from agentscope.state import AgentState

    state = AgentState(session_id="world-x:npc-a:conv-1")
    state.context = [
        UserMsg(name="player", content="你好"),
        AssistantMsg(name="npc-a", content="你好呀。"),
    ]
    raw = state.model_dump_json()
    restored = AgentState.model_validate_json(raw)
    assert restored.session_id == "world-x:npc-a:conv-1"
    assert len(restored.context) == 2
    assert restored.context[0].get_text_content() == "你好"
    assert restored.context[1].name == "npc-a"
    # Round-trip is stable: dumping again yields identical JSON.
    assert restored.model_dump_json() == raw


# ---------------------------------------------------------------------------
# Unregistered tools unavailable; no customer-service powers migrated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregistered_tools_are_unavailable():
    agent = make_agent()
    for name in ("shell", "bash", "execute_command", "read_file", "write_file",
                 "web_search", "run_python", "file_manager"):
        assert await agent.toolkit.get_tool(name) is None


@pytest.mark.asyncio
async def test_factory_exposes_no_shell_file_mcp_skills_workspace():
    agent = make_agent()
    schemas = await agent.toolkit.get_tool_schemas()
    names = {s.get("function", {}).get("name") for s in schemas}
    forbidden = {"shell", "bash", "read_file", "write_file", "edit_file",
                 "web_search", "run_python", "reset_tools", "skill_viewer"}
    assert not (names & forbidden)

    groups = agent.toolkit.tool_groups
    assert all(not group.mcps for group in groups)
    assert all(not getattr(group, "skills_or_loaders", None) for group in groups)
    # No customer-service workspace/offloader attached.
    assert agent.offloader is None


# ---------------------------------------------------------------------------
# Role profiles from configs/npcs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("npc_id", ["npc-a", "npc-b", "npc-c"])
async def test_npc_profile_loads_and_feeds_agent(npc_id):
    from core.agent.profiles import load_npc_profile

    profile = load_npc_profile(npc_id)
    assert profile.npc_id == npc_id
    assert profile.fallback_reply

    agent = make_agent(npc_id=npc_id, system_prompt=profile.system_prompt)
    prompt = await agent._get_system_prompt()
    assert profile.system_prompt.strip() in prompt


def test_unknown_npc_profile_is_rejected():
    from core.agent.profiles import load_npc_profile

    with pytest.raises(KeyError):
        load_npc_profile("npc-ghost")


def test_compression_prompt_is_not_customer_service_summary():
    """04 must not reuse the customer-service task/file-path summary;
    NPC semantics land fully in 07."""
    agent = make_agent()
    prompt = agent.context_config.compression_prompt
    for banned in ("文件路径", "API 端点", "任务和下一步计划",
                   "task_overview", "file paths", "未完成的任务"):
        assert banned not in prompt
    schema = agent.context_config.summary_schema
    blob = json.dumps(schema, ensure_ascii=False)
    for banned in ("task_overview", "file_paths", "next_steps", "tool_outputs"):
        assert banned not in blob
