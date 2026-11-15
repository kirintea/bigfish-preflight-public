def test_save_api_lists_reads_and_restores_new_epoch(client):
    run = client.post("/api/test/v1/runs", json={"name": "save"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    saved = client.post(base + "/saves")
    assert saved.status_code == 201
    snapshot_id = saved.json()["snapshot_id"]
    listed = client.get(base + "/saves")
    assert snapshot_id in [item["snapshot_id"] for item in listed.json()["items"]]
    read = client.get(base + f"/saves/{snapshot_id}")
    assert read.status_code == 200 and read.json()["content_version"] == "world-state-v1"
    restored = client.post(base + f"/saves/{snapshot_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["run_epoch"] != run["run_epoch"]
