from fastapi.testclient import TestClient

from core.config.schemas import AppConfig
from server import create_app
from state_helpers import run_report


def test_run_starts_with_isolated_identity(client):
    response = client.post("/api/test/v1/runs", json={"name": "baseline"})
    assert response.status_code == 201
    run = response.json()
    state = client.get(f"/api/test/v1/runs/{run['test_run_id']}/state")
    assert state.status_code == 200
    assert state.json()["revision"] == run["revision"] == 0
    assert state.json()["view"] == "management"
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    data = run_report(run)
    accepted = client.post(base + "/reports", json=data)
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["request_id"] == accepted.headers["x-request-id"]
    context = client.get(base + "/npcs/npc-a/context")
    assert context.json()["domains"]["body"]["data"]["present"] is True
    observed = client.get("/api/v1/observe/requests/" + context.headers["x-request-id"]).json()
    assert {s["stage"] for s in observed["stages"]} >= {"view_filter", "memory", "hooks", "model"}
    assert all(s["world_id"] == run["world_id"] for s in observed["stages"] if s["stage"] == "view_filter")


def test_test_adapter_rejects_spoofing_and_world_crossing(client):
    one, two = [client.post("/api/test/v1/runs", json={"name": name}).json() for name in ["one", "two"]]
    base = f"/api/test/v1/runs/{one['test_run_id']}"
    for data in [run_report(one, source_kind="simulation"), run_report(one, source_id="fake"), run_report(two)]:
        result = client.post(base + "/reports", json=data)
        assert result.status_code == 403
        assert result.json()["reason"] == "forbidden_source"
    assert client.get(base + "/npcs/ghost/context").status_code == 404
    assert client.get(base + "/state", headers={"Authorization": "Bearer test-sim-only"}).status_code == 403
    assert client.get(f"/api/v1/worlds/{one['world_id']}/npcs/npc-a/context").status_code == 403


def test_batch_route_and_unknown_fields(client):
    run = client.post("/api/test/v1/runs", json={"name": "batch"}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}"
    data = dict(batch_id="b1", expected_revision=0, reports=[run_report(run), run_report(run, "needs", {"hunger": 0.8})])
    result = client.post(base + "/reports/batch", json=data)
    assert result.status_code == 200
    assert result.json()["revision"] == 1
    invalid = client.post(base + "/reports", json={**run_report(run), "extra": True})
    assert invalid.status_code == 422
    assert invalid.json()["reason"] == "invalid_payload"


def test_production_registers_no_test_routes(tmp_path):
    config = AppConfig(environment="production", storage_dir=tmp_path, otel_enabled=False,
                       test_admin_token="admin", simulator_token="sim", simulator_world_ids={"world-a"},
                       simulator_source_ids={"sim-a"})
    with TestClient(create_app(config)) as client:
        assert not any(p.startswith("/api/test/") for p in client.get("/openapi.json").json()["paths"])
        for path, method in [("/runs", "post"), ("/runs/x/state", "get"), ("/runs/x/reports", "post"),
                             ("/runs/x/reports/batch", "post"), ("/runs/x/npcs/npc-a/context", "get")]:
            assert getattr(client, method)("/api/test/v1" + path).status_code == 404
        assert client.get("/api/v1/observe/status").status_code == 401
        client.app.state.worlds.create("production", "world-a", "epoch-a", ["npc-a", "npc-b"])
        from state_helpers import report
        client.headers["Authorization"] = "Bearer sim"
        assert client.post("/api/v1/worlds/world-a/npcs/npc-a/reports/body", json=report()).json()["status"] == "accepted"
        assert client.get("/api/v1/worlds/world-a/npcs/npc-a/state/body").status_code == 200
        assert client.get("/api/v1/worlds/other/npcs/npc-a/context").status_code == 403
        assert client.post("/api/v1/worlds/world-a/npcs/npc-b/reports/body", json=report()).status_code == 422
        assert client.get("/api/v1/worlds/world-a/state/resources").status_code == 422
        assert client.get("/api/v1/worlds/world-a/state/resources?npc_id=npc-a").status_code == 200


def test_http_deltas_preserve_omitted_fields_for_single_and_batch(client):
    run = client.post("/api/test/v1/runs", json={"name": "deltas"}).json()
    path = f"/api/test/v1/runs/{run['test_run_id']}"
    assert client.post(path + "/reports", json=run_report(run)).status_code == 200
    delta = run_report(run, payload={"awake": False}, mode="delta", sequence=2, expected_revision=1)
    assert client.post(path + "/reports", json=delta).status_code == 200
    view = client.get(path + "/npcs/npc-a/context").json()["domains"]["body"]["data"]
    assert view["present"] is True and view["awake"] is False
    batch_delta = run_report(run, payload={"can_speak": False}, mode="delta", sequence=3, expected_revision=2)
    assert client.post(path + "/reports/batch", json=dict(batch_id="delta-batch", expected_revision=2, reports=[batch_delta])).status_code == 200
    view = client.get(path + "/npcs/npc-a/context").json()["domains"]["body"]["data"]
    assert view["present"] is True and view["awake"] is False and view["can_speak"] is False


def test_validation_rejection_is_observable_without_payload(client):
    run = client.post("/api/test/v1/runs", json={"name": "invalid"}).json()
    path = f"/api/test/v1/runs/{run['test_run_id']}"
    invalid = client.post(path + "/reports", json=run_report(run, "needs", {"hunger": 2.0,
        "influences": [{"name": "private-sadness", "value": 0.5, "source": "secret"}]}))
    assert invalid.status_code == 422
    assert invalid.json()["errors"]
    observed = client.get("/api/v1/observe/requests/" + invalid.headers["x-request-id"]).json()
    assert any(s["stage"] == "report_validate" and s["status"] == "rejected" and s["reason"] == "invalid_payload" for s in observed["stages"])
    assert "private-sadness" not in __import__("json").dumps(observed)


def test_report_auth_errors_use_fixed_response(client):
    client.headers.pop("Authorization")
    result = client.post("/api/v1/worlds/world-a/reports", json={})
    assert result.status_code == 401
    assert set(result.json()) >= {"status", "reason", "report_id", "request_id", "trace_id", "revision", "event_ids"}
