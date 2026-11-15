def test_hook_api_lists_registered_hooks_and_activates_only_trusted_event(client):
    run = client.post("/api/test/v1/runs", json={"name": "hooks"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    hooks = client.get(base + "/hooks")
    assert hooks.status_code == 200
    assert any(item["hook_id"] == "harvest-public" for item in hooks.json()["hooks"])

    rejected = client.post(base + "/hooks/harvest-public/activate", json={"event_id": "missing"})
    assert rejected.status_code == 404
    assert rejected.json()["detail"] == "event_not_found"


def test_hook_api_requires_registered_definition_and_persists_activation(client):
    run = client.post("/api/test/v1/runs", json={"name": "hooks"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    from state_helpers import run_report
    event = run_report(run, "events", {"events": [{"event_id": "harvest-1", "fact": "harvest", "observers": ["npc-a"]}]}, entity_id=run["world_id"])
    assert client.post(base + "/reports", json=event).json()["status"] == "accepted"
    activated = client.post(base + "/hooks/harvest-public/activate", json={
        "event_id": "harvest-1", "npc_ids": ["npc-a"]
    })
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert activated.json()["event_id"] == "harvest-1"
    preview = client.get(base + "/hooks/preview/npc-a")
    assert preview.status_code == 200
    assert preview.json()["prompt"] == "Public harvest background"
    unknown = client.post(base + "/hooks/nope/activate", json={"event_id": "harvest-1"})
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "hook_not_registered"
    deactivated = client.post(base + "/hooks/harvest-public/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "revoked"
    assert client.get(base + "/hooks/preview/npc-a").json()["prompt"] == ""
