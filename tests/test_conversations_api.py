def test_autonomous_conversation_api_creates_three_npc_session_and_advances(client):
    run = client.post("/api/test/v1/runs", json={"name": "auto-chat"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    created = client.post(base + "/conversations/autonomous", json={
        "members": ["npc-a", "npc-b", "npc-c"], "topic": "tide"
    })
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["mode"] == "npc_autonomous"
    cid = conversation["conversation_id"]
    opportunity = client.post(base + f"/conversations/autonomous/{cid}/opportunities", json={"trigger": "opening"})
    assert opportunity.status_code == 200
    assert opportunity.json()["opportunity_id"] == client.post(
        base + f"/conversations/autonomous/{cid}/opportunities", json={"trigger": "opening"}
    ).json()["opportunity_id"]
    advanced = client.post(base + f"/conversations/autonomous/{cid}/advance", json={"trigger": "opening"})
    assert advanced.status_code == 200
    assert advanced.json()["message"]["actual_recipient_ids"]


def test_autonomous_api_rejects_player_and_keeps_member_revision(client):
    run = client.post("/api/test/v1/runs", json={"name": "auto-chat"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    rejected = client.post(base + "/conversations/autonomous", json={"members": ["player", "npc-a"]})
    assert rejected.status_code == 422
