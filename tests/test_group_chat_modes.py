from uuid import uuid4


def make_chat(client, interaction_mode="disabled"):
    run = client.post("/api/test/v1/runs", json={
        "name": "group-modes", "npc_ids": ["npc-bigfish", "npc-claude"],
    }).json()
    path = f"/api/test/v1/runs/{run['test_run_id']}"
    created = client.post(path + "/conversations", json={
        "command_id": uuid4().hex,
        "run_epoch": run["run_epoch"],
        "expected_revision": run["revision"],
        "members": ["player", "npc-bigfish", "npc-claude"],
        "interaction_mode": interaction_mode,
    })
    assert created.status_code == 201
    return path, created.json()


def test_chat_persists_interaction_mode_and_returns_generation_targets(client):
    path, chat = make_chat(client, "forced")
    assert chat["interaction_mode"] == "forced"
    message = client.post(
        f"{path}/conversations/{chat['conversation_id']}/messages",
        json={
            "command_id": uuid4().hex,
            "run_epoch": chat["run_epoch"],
            "expected_revision": chat["revision"],
            "text": "大家都说说看。",
            "generate": True,
        },
    )
    assert message.status_code == 200
    assert message.json()["generation_targets"] == ["npc-bigfish", "npc-claude"]


def test_chat_context_exposes_other_members_messages(client):
    path, chat = make_chat(client, "forced")
    message = client.post(
        f"{path}/conversations/{chat['conversation_id']}/messages",
        json={
            "command_id": uuid4().hex,
            "run_epoch": chat["run_epoch"],
            "expected_revision": chat["revision"],
            "text": "请一起讨论。",
            "generate": True,
        },
    ).json()
    npc_turn = client.post(
        f"{path}/conversations/{chat['conversation_id']}/turns",
        json={
            "turn_id": "bigfish-1", "request_id": "bigfish-1",
            "text": "请一起讨论。", "npc_id": "npc-bigfish",
        },
    )
    assert npc_turn.status_code == 202
    latest = client.get(f"{path}/conversations/{chat['conversation_id']}").json()
    assert any(m["author"] == "npc-bigfish" for m in latest["messages"])
    context = client.get(
        f"{path}/conversations/{chat['conversation_id']}/context/npc-claude"
    )
    assert context.status_code == 200
    assert any(m["author"] == "npc-bigfish" for m in context.json()["messages"])


def test_chat_stream_endpoint_returns_sse_events(client):
    path, chat = make_chat(client, "disabled")
    response = client.post(
        f"{path}/conversations/{chat['conversation_id']}/messages",
        json={
            "command_id": uuid4().hex,
            "run_epoch": chat["run_epoch"],
            "expected_revision": chat["revision"],
            "text": "你好。",
            "generate": True,
        },
    )
    assert response.status_code == 200
    with client.stream(
        "POST",
        f"{path}/conversations/{chat['conversation_id']}/turns/stream",
        json={
            "turn_id": "stream-1", "request_id": "stream-1",
            "text": "你好。", "npc_id": "npc-bigfish",
        },
    ) as streamed:
        assert streamed.status_code == 200
        body = "".join(streamed.iter_text())
    assert "event: delta" in body
    assert "event: result" in body


def test_scheduler_disabled_unless_explicitly_forced_and_observes_previous_npc(client, monkeypatch):
    from core.agent.offline_model import OfflineChatModel
    calls = []
    original = OfflineChatModel._call_api
    async def capture(self, model_name, messages, *args, **kwargs):
        calls.append([m.get_text_content() for m in messages])
        return await original(self, model_name, messages, *args, **kwargs)
    monkeypatch.setattr(OfflineChatModel, '_call_api', capture)
    path, chat = make_chat(client)
    endpoint = f"{path}/conversations/{chat['conversation_id']}/turns"
    body = dict(turn_id='npc-1', request_id='npc-1', text='Start a conversation',
        npc_id='npc-bigfish', trigger='scheduler')
    assert client.post(endpoint, json=body).status_code == 409
    first = client.post(endpoint, json={**body, 'force': True})
    assert first.status_code == 202
    second = client.post(endpoint, json={**body, 'force': True, 'npc_id': 'npc-claude',
        'turn_id': 'npc-2', 'request_id': 'npc-2'})
    assert second.status_code == 202
    assert any('npc-bigfish: ' + first.json()['utterance'] in m for m in calls[1])


def test_non_member_cannot_generate_group_reply(client):
    path, chat = make_chat(client)
    assert client.post(f"{path}/conversations/{chat['conversation_id']}/turns", json={
        'turn_id': 'bad', 'npc_id': 'npc-ghost', 'text': 'hello'}).status_code == 422
