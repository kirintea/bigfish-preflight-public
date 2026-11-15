def test_memory_api_writes_searches_and_compresses_with_sources(client):
    run = client.post("/api/test/v1/runs", json={"name": "memory"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    from state_helpers import run_report
    event = run_report(run, "events", {"events": [{"event_id": "e1", "fact": "gold", "observers": ["npc-a"]}]}, entity_id=run["world_id"])
    assert client.post(base + "/reports", json=event).json()["status"] == "accepted"
    created = client.post(base + "/npcs/npc-a/memory", json={"source_event_ids": ["e1"], "content": "gold found", "acquisition": "direct"})
    assert created.status_code == 201
    listed = client.get(base + "/npcs/npc-a/memory?query=gold")
    assert listed.status_code == 200 and listed.json()["items"][0]["source_event_ids"] == ["e1"]
    compressed = client.post(base + "/npcs/npc-a/memory/compress", json={"memory_ids": [created.json()["memory_id"]]})
    assert compressed.status_code == 200
    assert compressed.json()["candidate"]["source_refs"] == ["e1"]
