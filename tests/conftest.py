import pytest
from fastapi.testclient import TestClient

from core.config.schemas import AppConfig
from server import create_app


@pytest.fixture
def client(tmp_path):
    config = AppConfig(
        environment="test", storage_dir=tmp_path,
        test_control_enabled=True, otel_enabled=False,
        test_admin_token="test-admin-only", simulator_token="test-sim-only",
    )
    with TestClient(create_app(config)) as instance:
        instance.headers["Authorization"] = "Bearer test-admin-only"
        yield instance
