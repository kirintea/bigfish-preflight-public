from dataclasses import FrozenInstanceError

import pytest

from core.auth import Principal, require_source


def test_management_observation_requires_authentication(client):
    client.headers.pop("Authorization")
    response = client.get("/api/v1/observe/status?viewer=root&source_kind=simulator")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_simulator_cannot_observe_even_with_claimed_admin_fields(client):
    response = client.get("/api/v1/observe/status?viewer=root", headers={
        "Authorization": "Bearer test-sim-only", "X-Role": "test_admin", "X-Source-Kind": "test_admin",
    })
    assert response.status_code == 403


@pytest.mark.parametrize("credential", ["Bearer invalid", "Basic test-admin-only", "Bearer"])
def test_invalid_credentials_are_unauthorized(client, credential):
    assert client.get("/api/v1/observe/status", headers={"Authorization": credential}).status_code == 401


def test_admin_can_observe_and_metrics_are_protected(client):
    assert client.get("/api/v1/observe/status").status_code == 200
    assert client.get("/metrics").status_code == 200
    client.headers.pop("Authorization")
    assert client.get("/metrics").status_code == 401


def test_principal_is_immutable_and_sources_are_server_scoped():
    principal = Principal("simulation", "simulator", frozenset({"w1"}), frozenset({"source-1"}))
    require_source(principal, "w1", "source-1")
    with pytest.raises(FrozenInstanceError):
        principal.role = "test_admin"
    with pytest.raises(Exception) as error:
        require_source(principal, "w2", "source-1")
    assert error.value.status_code == 403
