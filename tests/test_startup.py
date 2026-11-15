import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from core.config.schemas import AppConfig
from server import create_app


def test_health_has_version_and_real_local_request_stages(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
    request_id, trace_id = response.headers["x-request-id"], response.headers["x-trace-id"]
    assert response.json()["request_id"] == request_id
    view = client.get(f"/api/v1/observe/requests/{request_id}")
    assert view.status_code == 200
    assert view.json()["trace_id"] == trace_id
    assert {s["stage"] for s in view.json()["stages"]} == {"request", "health"}
    assert view.json()["stages"][-1]["status"] == "ok"


def test_production_has_no_test_routes_or_default_credentials(tmp_path):
    with TestClient(create_app(AppConfig(environment="production", storage_dir=tmp_path))) as client:
        assert not any(path.startswith("/api/test/") for path in client.get("/openapi.json").json()["paths"])
        assert client.get("/api/v1/observe/status", headers={"Authorization": "Bearer test-admin-only"}).status_code == 401
        assert client.get("/health").status_code == 200


def test_unwritable_required_local_storage_fails_startup(tmp_path):
    target = tmp_path / "file-instead-of-directory"
    target.write_text("blocked")
    with pytest.raises(OSError):
        with TestClient(create_app(AppConfig(storage_dir=target))):
            pass


def test_missing_collector_does_not_block_health(tmp_path):
    config = AppConfig(storage_dir=tmp_path, otlp_enabled=True, otlp_endpoint="http://127.0.0.1:1",
                       shutdown_timeout_seconds=0.05)
    with TestClient(create_app(config)) as client:
        assert client.get("/health").status_code == 200


def test_request_traceparent_is_extracted_and_outgoing_context_injected(tmp_path):
    exporter = InMemorySpanExporter()
    app = create_app(AppConfig(storage_dir=tmp_path), span_exporter=exporter)
    trace_id = "1234567890abcdef1234567890abcdef"
    with TestClient(app) as client:
        response = client.get("/health", headers={
            "traceparent": f"00-{trace_id}-1234567890abcdef-01", "X-Request-ID": "untrusted-id",
        })
        assert response.headers["x-trace-id"] == trace_id
        assert trace_id in response.headers["traceparent"]
        assert response.headers["x-request-id"] != "untrusted-id"
        assert app.state.tracing.force_flush(1)
        assert not exporter.get_finished_spans()
        records = app.state.events.get(response.headers["x-request-id"])
        assert records["trace_id"] == trace_id
        assert {record["stage"] for record in records["stages"]} == {"request", "health"}


def test_secrets_and_query_payload_never_reach_logs_spans_or_stages(tmp_path, caplog, capsys):
    exporter = InMemorySpanExporter()
    config = AppConfig(storage_dir=tmp_path, test_admin_token="secret-admin", simulator_token="secret-sim")
    app = create_app(config, span_exporter=exporter)
    with TestClient(app) as client:
        response = client.get("/health?dialogue=secret-dialogue", headers={"Authorization": "Bearer secret-admin"})
        assert response.status_code == 200
        client.get("/api/v1/observe/status", headers={"Authorization": "Bearer secret-sim"})
        app.state.tracing.force_flush(1)
    captured = capsys.readouterr()
    text = captured.err + captured.out + str(exporter.get_finished_spans())
    text += (tmp_path / "observe" / "stages.jsonl").read_text()
    text += "".join(path.read_text() for path in (tmp_path / "logs").glob("*.log"))
    assert not any(secret in text for secret in ("secret-admin", "secret-sim", "secret-dialogue"))


def test_unhandled_errors_have_safe_correlated_response(tmp_path):
    app = create_app(AppConfig(storage_dir=tmp_path))

    @app.get("/explode")
    async def explode():
        raise RuntimeError("secret-error")

    with TestClient(app) as client:
        response = client.get("/explode")
        assert response.status_code == 500
        assert response.json()["request_id"] == response.headers["x-request-id"]
        assert "secret-error" not in response.text
        records = app.state.events.get(response.headers["x-request-id"])
        assert records["stages"][-1]["status"] == "error"


def test_lifespan_cancels_background_tasks(tmp_path):
    app = create_app(AppConfig(storage_dir=tmp_path))

    @app.get("/start-task")
    async def start_task():
        app.state.background_tasks.add(asyncio.create_task(asyncio.sleep(3600)))
        return {}

    with TestClient(app) as client:
        client.get("/start-task")
        task = next(iter(app.state.background_tasks))
        assert not task.done()
    assert task.cancelled()


def test_untrusted_tracestate_and_baggage_are_not_propagated(tmp_path):
    exporter = InMemorySpanExporter()
    app = create_app(AppConfig(storage_dir=tmp_path), span_exporter=exporter)
    with TestClient(app) as client:
        response = client.get("/health", headers={
            "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
            "tracestate": "example=private-trace-secret", "baggage": "dialogue=private-baggage-secret",
        })
        assert app.state.tracing.force_flush(1)
        assert "tracestate" not in response.headers
        assert "baggage" not in response.headers
        assert all(not span.context.trace_state for span in exporter.get_finished_spans())


async def test_invalid_trace_header_bytes_start_a_new_correlated_request(tmp_path):
    app = create_app(AppConfig(storage_dir=tmp_path))
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
             "scheme": "http", "path": "/health", "raw_path": b"/health", "query_string": b"",
             "root_path": "", "headers": [(b"traceparent", b"\xff")],
             "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8091)}
    async with app.router.lifespan_context(app):
        await app(scope, receive, send)
    assert messages[0]["status"] == 200
    headers = dict(messages[0]["headers"])
    body = json.loads(messages[1]["body"])
    assert headers[b"x-request-id"].decode() == body["request_id"]
    assert len(headers[b"x-trace-id"]) == 32


def test_shutdown_timeout_is_persisted_after_lifespan(tmp_path):
    class StuckShutdownExporter(InMemorySpanExporter):
        def shutdown(self):
            release.wait(5)

    release = threading.Event()
    app = create_app(AppConfig(storage_dir=tmp_path, shutdown_timeout_seconds=0.03),
                     span_exporter=StuckShutdownExporter())
    try:
        with TestClient(app) as client:
            client.get("/health")
            assert app.state.tracing.force_flush(1)
            started = time.monotonic()
        assert time.monotonic() - started < 0.3
        status = json.loads((tmp_path / "observe" / "shutdown-status.json").read_text())
        assert status["shutdown_timeouts"] == 1
        assert status["background_shutdown_timeouts"] == 0
    finally:
        release.set()
        app.state.tracing.processor.worker.join(1)
