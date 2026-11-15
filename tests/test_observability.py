import asyncio
import json
import threading
import time

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from core.config.schemas import AppConfig
from core.tracing.context import RequestContext, current_request, request_scope
from core.tracing.decorators import stage
from core.tracing.events import EventStore
from core.tracing.metrics import Metrics
from core.tracing.setup import TracingSetup


def resources(tmp_path, exporter=None, **kwargs):
    config = AppConfig(storage_dir=tmp_path, **kwargs)
    store = EventStore(config)
    tracing = TracingSetup(config, store, exporter=exporter)
    return store, tracing


async def test_concurrent_worlds_and_child_tasks_keep_parent_span(tmp_path):
    exporter = InMemorySpanExporter()
    store, tracing = resources(tmp_path, exporter)
    global_provider = trace.get_tracer_provider()

    async def run(world):
        with tracing.tracer.start_as_current_span("root") as parent:
            context = RequestContext.from_span(world, parent, world_id=world, run_epoch=2)
            with request_scope(context):
                async def child():
                    await asyncio.sleep(0)
                    assert current_request.get() == context
                    with stage(tracing, store, "health"):
                        assert trace.get_current_span().get_span_context().trace_id == parent.get_span_context().trace_id
                await asyncio.create_task(child())

    await asyncio.gather(run("world-a"), run("world-b"))
    assert tracing.force_flush(1)
    spans = exporter.get_finished_spans()
    assert len(spans) == 4
    for world in ("world-a", "world-b"):
        record = store.get(world)
        child = next(s for s in spans if s.name == "health" and f"{s.context.trace_id:032x}" == record["trace_id"])
        parent = next(s for s in spans if s.context.span_id == child.parent.span_id)
        assert parent.name == "root"
        assert all(s["world_id"] == world and s["run_epoch"] == 2 for s in record["stages"])
        assert [s["status"] for s in record["stages"]] == ["started", "ok"]
    assert current_request.get() is None
    assert trace.get_tracer_provider() is global_provider
    assert tracing.shutdown(1)


class FailedExporter(SpanExporter):
    def export(self, spans):
        raise RuntimeError("private-token-and-payload")

    def shutdown(self):
        pass


def test_export_failure_preserves_local_records_without_secret(tmp_path, caplog, capsys):
    store, tracing = resources(tmp_path, FailedExporter())
    with tracing.tracer.start_as_current_span("root") as span:
        with request_scope(RequestContext.from_span("request-a", span)):
            with stage(tracing, store, "health"):
                pass
    assert tracing.force_flush(1)
    assert store.get("request-a")["stages"][-1]["status"] == "ok"
    assert store.status()["export_errors"] >= 1
    assert "private-token" not in json.dumps(store.status()) + caplog.text + capsys.readouterr().err
    assert tracing.shutdown(1)


def test_capacity_rotation_and_skipped_are_visible(tmp_path):
    store, tracing = resources(tmp_path, observation_capacity=4, journal_max_bytes=1024, journal_backups=1)
    for index in range(20):
        with tracing.tracer.start_as_current_span("root") as span:
            with request_scope(RequestContext.from_span(f"req-{index}", span)):
                store.append(current_request.get(), "auth", "rejected", "unauthenticated")
                with stage(tracing, store, "health", skipped=True):
                    pass
    assert store.get("req-0") is None
    assert store.get("req-19")["stages"][-1]["status"] == "skipped"
    assert store.status()["dropped_records"] > 0
    assert store.status()["rotations"] > 0
    assert store.status()["records"] <= 4
    assert len(list((tmp_path / "observe").glob("stages*"))) <= 2
    assert all(p.stat().st_size <= 1024 for p in (tmp_path / "observe").glob("stages*"))
    tracing.shutdown(1)


class BlockingExporter(SpanExporter):
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def export(self, spans):
        self.entered.set()
        self.release.wait(5)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def test_hung_export_has_deadline_and_queue_drop_counter(tmp_path):
    exporter = BlockingExporter()
    store, tracing = resources(tmp_path, exporter, export_queue_capacity=1)
    try:
        with tracing.tracer.start_as_current_span("first"):
            pass
        assert exporter.entered.wait(1)
        for _ in range(10):
            with tracing.tracer.start_as_current_span("extra"):
                pass
        started = time.monotonic()
        assert not tracing.force_flush(0.03)
        assert not tracing.shutdown(0.03)
        assert time.monotonic() - started < 0.3
        assert store.status()["export_dropped"] > 0
        assert store.status()["shutdown_timeouts"] == 1
    finally:
        exporter.release.set()


def test_sampling_is_reported_but_local_stages_are_retained(tmp_path):
    exporter = InMemorySpanExporter()
    store, tracing = resources(tmp_path, exporter, trace_sample_ratio=0)
    with tracing.tracer.start_as_current_span("root") as span:
        with request_scope(RequestContext.from_span("unsampled", span)):
            with stage(tracing, store, "health"):
                pass
    assert tracing.force_flush(1)
    assert not exporter.get_finished_spans()
    assert store.get("unsampled")
    assert store.status()["sampled_out"] >= 1
    tracing.shutdown(1)


def test_metrics_reject_high_cardinality_values():
    metrics = Metrics()
    metrics.record("health", "ok", "none", 1)
    metrics.record("world-secret", "request-secret", "npc-secret", 1)
    output = metrics.render().decode()
    assert 'stage="health"' in output
    assert 'stage="other"' in output
    assert not any(value in output for value in ("world-secret", "request-secret", "npc-secret"))


def test_exception_is_sanitized_in_stage_and_span(tmp_path):
    exporter = InMemorySpanExporter()
    store, tracing = resources(tmp_path, exporter)
    with tracing.tracer.start_as_current_span("root", record_exception=False, set_status_on_exception=False) as span:
        with request_scope(RequestContext.from_span("failed", span)):
            with pytest.raises(RuntimeError):
                with stage(tracing, store, "health"):
                    raise RuntimeError("private-token-and-dialogue")
    assert tracing.force_flush(1)
    assert store.get("failed")["stages"][-1]["reason"] == "internal_error"
    assert "private-token" not in str(exporter.get_finished_spans())
    assert "private-token" not in (tmp_path / "observe" / "stages.jsonl").read_text()
    tracing.shutdown(1)
