from uuid import uuid4
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from core.agent.turns import ModelTurnError, TurnRequest
from core.config.schemas import AppConfig
from server import create_app


def observed_app(tmp_path, *, mode="valid_reply", enabled=True):
    exporter = InMemorySpanExporter()
    app = create_app(AppConfig(storage_dir=tmp_path, offline_mode=True,
        offline_model_mode=mode, otel_enabled=enabled), span_exporter=exporter)

    @app.post("/execute")
    async def execute():
        world = app.state.turns.create_world(["npc-a"])
        return await app.state.turns.submit_async(world.world_id, TurnRequest(
            request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
            speaker_id="player", trigger="player_message", text="private-dialogue"))

    @app.get("/explode")
    async def explode():
        raise RuntimeError("private-error")

    return app, exporter


def test_polling_and_buttons_do_not_export_or_log_success(tmp_path):
    app, exporter = observed_app(tmp_path)
    with TestClient(app) as client:
        for path in ("/health", "/openapi.json", "/missing", "/api/v1/observe/status"):
            client.get(path)
        assert app.state.tracing.force_flush(1)
        assert not exporter.get_finished_spans()
        assert client.get("/explode").status_code == 500
    logs = (tmp_path / "logs" / "agent-server.log").read_text(encoding="utf-8")
    assert "request_completed" not in logs
    assert "ERROR | request_failed" in logs
    assert "private-error" not in logs


@pytest.mark.parametrize("mode", ["valid_reply", "timeout", "invalid_json"])
def test_agent_execution_exports_connected_stages_and_result(tmp_path, mode):
    app, exporter = observed_app(tmp_path, mode=mode)
    trace_id = "1234567890abcdef1234567890abcdef"
    with TestClient(app) as client:
        response = client.post("/execute", headers={
            "traceparent": f"00-{trace_id}-1234567890abcdef-01"})
        assert response.status_code == 200
        assert app.state.tracing.force_flush(1)
        spans = exporter.get_finished_spans()
    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"invoke_agent npc-a", "chat offline-script"}
    turn, model = by_name["invoke_agent npc-a"], by_name["chat offline-script"]
    assert turn.parent.span_id == int("1234567890abcdef", 16)
    assert model.parent.span_id == turn.context.span_id
    assert all(span.instrumentation_scope.name == "agentscope" for span in spans)
    assert all(span.context.trace_id == int(trace_id, 16) for span in spans)
    assert turn.attributes["bigfish.turn.id"] == "t1"
    assert turn.attributes["bigfish.npc.id"] == "npc-a"
    assert "private-dialogue" in model.attributes["gen_ai.input.messages"]
    assert "gen_ai.output.messages" in turn.attributes or mode != "valid_reply"
    if mode == "valid_reply":
        assert turn.status.status_code != StatusCode.ERROR
        assert "gen_ai.output.messages" in model.attributes
    else:
        assert (model.status.status_code == StatusCode.ERROR) == (mode == "timeout")
        assert turn.status.status_code == StatusCode.ERROR
    logs = (tmp_path / "logs" / "agent-server.log").read_text(encoding="utf-8")
    assert "INFO" not in logs
    assert "agent_turn_started" not in logs
    assert "agent_turn_completed" not in logs
    assert bool(logs) == (mode != "valid_reply")
    assert "private-dialogue" not in logs


def test_disabled_observation_does_not_export_agent_spans(tmp_path):
    app, exporter = observed_app(tmp_path, enabled=False)
    with TestClient(app) as client:
        assert client.post("/execute").json()["status"] == "succeeded"
        assert app.state.tracing.force_flush(1)
    assert not exporter.get_finished_spans()


def test_successful_requests_and_turns_do_not_write_journal(tmp_path):
    app, _ = observed_app(tmp_path)
    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/health").status_code == 200
        assert client.post("/execute").json()["status"] == "succeeded"
    assert (tmp_path / "observe" / "stages.jsonl").read_text() == ""
    assert (tmp_path / "logs" / "agent-server.log").read_text() == ""


def test_native_root_has_no_missing_http_parent(tmp_path):
    app, exporter = observed_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/execute")
        assert app.state.tracing.force_flush(1)
        root = next(span for span in exporter.get_finished_spans() if span.name.startswith("invoke_agent "))
        assert root.parent is None
        assert f"{root.context.trace_id:032x}" == response.headers["x-trace-id"]


@pytest.mark.parametrize("path", ["configs/test.yaml", "configs/dev.yaml"])
def test_local_configs_export_to_collector_by_default(monkeypatch, path):
    from core.config.manager import ConfigManager

    monkeypatch.delenv("BIGFISH_OTLP_ENABLED", raising=False)
    monkeypatch.delenv("BIGFISH_OTLP_ENDPOINT", raising=False)
    config = ConfigManager().load(path)
    assert config.otlp_enabled is True
    assert config.otlp_endpoint == "http://127.0.0.1:4317"


async def test_framework_stream_stays_open_and_cancellation_finishes_spans(tmp_path):
    from agentscope.message import TextBlock
    from agentscope.model import ChatResponse

    app, exporter = observed_app(tmp_path)
    async with app.router.lifespan_context(app):
        service = app.state.turns
        world = service.create_world(["npc-a"])
        session = await service.sessions.get_or_create(namespace="test", world_id=world.world_id,
            npc_id="npc-a", conversation_id="c1", run_epoch=world.run_epoch)
        first_delta, closed = asyncio.Event(), asyncio.Event()

        async def chunks():
            try:
                yield ChatResponse(content=[TextBlock(text="hello")], is_last=False)
                await asyncio.Event().wait()
            finally:
                closed.set()

        async def call(*args, **kwargs):
            return chunks()

        async def delta(text):
            first_delta.set()

        session.agent.model._call_api = call
        request = TurnRequest(request_id="stream-r", conversation_id="c1", turn_id="stream-t",
            speaker_id="player", trigger="player_message", text="hello")
        task = asyncio.create_task(service.submit_async(world.world_id, request, on_delta=delta))
        try:
            await asyncio.wait_for(first_delta.wait(), 2)
            assert app.state.tracing.force_flush(1)
            assert not exporter.get_finished_spans()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert closed.is_set()
        assert session.state.context == []
        assert app.state.tracing.force_flush(1)
        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {"invoke_agent npc-a", "chat offline-script"}
        assert all(span.status.status_code == StatusCode.ERROR for span in spans)


async def test_framework_trace_contains_complete_stream_without_duplicate_deltas(tmp_path):
    from agentscope.message import TextBlock
    from agentscope.model import ChatResponse

    app, exporter = observed_app(tmp_path)
    async with app.router.lifespan_context(app):
        service = app.state.turns
        world = service.create_world(["npc-a"])
        session = await service.sessions.get_or_create(namespace="test", world_id=world.world_id,
            npc_id="npc-a", conversation_id="c1", run_epoch=world.run_epoch)

        async def chunks():
            yield ChatResponse(content=[TextBlock(text="hello")], is_last=False)
            yield ChatResponse(content=[TextBlock(text=" world")], is_last=False)
            yield ChatResponse(content=[], is_last=False)

        async def call(*args, **kwargs):
            return chunks()

        received = []

        async def delta(text):
            received.append(text)

        session.agent.model._call_api = call
        result = await service.submit_async(world.world_id, TurnRequest(request_id="stream-r",
            conversation_id="c1", turn_id="t1", speaker_id="player", trigger="player_message",
            text="hello"), on_delta=delta)
        assert result.utterance == "hello world"
        assert received == ["hello", " world"]
        assert app.state.tracing.force_flush(1)
        model = next(span for span in exporter.get_finished_spans() if span.name.startswith("chat "))
        messages = json.loads(model.attributes["gen_ai.output.messages"])
        assert "".join(part["content"] for part in messages[0]["parts"]) == "hello world"


async def test_framework_provider_routes_concurrent_apps_without_cross_export(tmp_path):
    first, first_exporter = observed_app(tmp_path / "first")
    second, second_exporter = observed_app(tmp_path / "second")
    async with first.router.lifespan_context(first), second.router.lifespan_context(second):
        async def run(app, npc_id):
            service = app.state.turns
            world = service.create_world([npc_id])
            result = await service.submit_async(world.world_id, TurnRequest(
                request_id=uuid4().hex, conversation_id="c1", turn_id="t1",
                speaker_id="player", trigger="player_message", text="hello"), npc_id=npc_id)
            assert result.status == "succeeded"

        await asyncio.gather(run(first, "npc-a"), run(second, "npc-b"))
        for app, exporter, npc_id in ((first, first_exporter, "npc-a"),
                                      (second, second_exporter, "npc-b")):
            assert app.state.tracing.force_flush(1)
            spans = exporter.get_finished_spans()
            assert {span.name for span in spans} == {f"invoke_agent {npc_id}", "chat offline-script"}
