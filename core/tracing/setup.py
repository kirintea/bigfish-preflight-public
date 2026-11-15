"""Application-scoped tracing providers, resources, and export lifecycle."""

import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry import trace
from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.trace.sampling import Decision, Sampler, TraceIdRatioBased
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator

from .context import current_request


_agent_provider = ContextVar("agent_tracer_provider", default=None)
_provider_lock = threading.Lock()


class RequestTraceIdGenerator(RandomIdGenerator):
    def generate_trace_id(self):
        request = current_request.get()
        if request is not None:
            return int(request.trace_id, 16)
        return super().generate_trace_id()


class AgentTracerProvider(TracerProvider):
    """Route AgentScope's global tracer lookup to the executing application."""

    def get_tracer(self, *args, **kwargs):
        provider = _agent_provider.get()
        if provider is None:
            return trace.NoOpTracer()
        return provider.get_tracer(*args, **kwargs)


def initialize_agent_tracing():
    with _provider_lock:
        provider = trace.get_tracer_provider()
        if isinstance(provider, AgentTracerProvider):
            return
        if not isinstance(provider, trace.ProxyTracerProvider):
            raise RuntimeError("AgentScope tracing requires the application tracer provider")
        trace.set_tracer_provider(AgentTracerProvider(shutdown_on_exit=False))


class CountingSampler(Sampler):
    def __init__(self, ratio, store):
        self.delegate = TraceIdRatioBased(ratio)
        self.store = store

    def should_sample(self, *args, **kwargs):
        result = self.delegate.should_sample(*args, **kwargs)
        if result.decision == Decision.DROP:
            self.store.increment("sampled_out")
        return result

    def get_description(self):
        return self.delegate.get_description()


class BoundedExportProcessor(SpanProcessor):
    """A bounded SDK export queue with a deadline independent of exporter behavior."""

    def __init__(self, exporter, store, capacity, *, agent_only=False):
        self.exporter, self.store, self.capacity = exporter, store, capacity
        self.agent_only = agent_only
        self.condition = threading.Condition()
        self.queue = deque()
        self.in_flight = False
        self.closed = False
        self.worker = threading.Thread(target=self._run, name="agent-span-export", daemon=True)
        self.worker.start()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        if self.agent_only and span.instrumentation_scope.name != "agentscope":
            return
        with self.condition:
            if self.closed or len(self.queue) >= self.capacity:
                self.store.increment("export_dropped")
                return
            self.queue.append(span)
            self.condition.notify_all()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.queue or self.closed)
                if not self.queue and self.closed:
                    break
                batch = tuple(self.queue.popleft() for _ in range(min(128, len(self.queue))))
                self.in_flight = True
            try:
                result = self.exporter.export(batch)
                if result == SpanExportResult.SUCCESS:
                    self.store.increment("exported_spans", len(batch))
                else:
                    self.store.increment("export_errors")
            except Exception:
                # Exporter exceptions can include endpoint credentials and payloads.
                self.store.increment("export_errors")
            finally:
                with self.condition:
                    self.in_flight = False
                    self.condition.notify_all()
        try:
            self.exporter.shutdown()
        except Exception:
            self.store.increment("export_errors")

    def force_flush(self, timeout_millis=30000):
        with self.condition:
            return self.condition.wait_for(
                lambda: not self.queue and not self.in_flight, max(0, timeout_millis / 1000)
            )

    def shutdown(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class TracingSetup:
    def __init__(self, config, store, exporter=None, *, agent_only=False):
        self.config, self.store = config, store
        if agent_only and config.otel_enabled:
            initialize_agent_tracing()
        self.provider = TracerProvider(
            resource=Resource({"service.name": config.service_name, "service.version": config.service_version,
                               "deployment.environment": config.environment}),
            sampler=CountingSampler(config.trace_sample_ratio if config.otel_enabled else 0, store),
            id_generator=RequestTraceIdGenerator(),
            shutdown_on_exit=False,
        )
        if exporter is None and config.otlp_enabled:
            exporter = OTLPSpanExporter(
                endpoint=config.otlp_endpoint, timeout=config.shutdown_timeout_seconds,
                headers={key: value.get_secret_value() for key, value in config.otlp_headers.items()},
            )
        self.processor = None
        if exporter is not None and config.otel_enabled:
            self.processor = BoundedExportProcessor(exporter, store, config.export_queue_capacity,
                                                    agent_only=agent_only)
            self.provider.add_span_processor(self.processor)
        self.tracer = self.provider.get_tracer("bigfish-agent", config.service_version)

    @contextmanager
    def agent_scope(self):
        token = _agent_provider.set(self.provider)
        request = current_request.get()
        parent = request.parent_context if request else None
        context_token = otel_context.attach(parent if parent is not None else otel_context.Context())
        try:
            yield
        finally:
            otel_context.detach(context_token)
            _agent_provider.reset(token)

    def force_flush(self, timeout_seconds):
        result = self.provider.force_flush(timeout_millis=max(1, int(timeout_seconds * 1000)))
        if not result:
            self.store.increment("flush_timeouts")
        return result

    def shutdown(self, timeout_seconds):
        started = time.monotonic()
        self.provider.shutdown()
        if self.processor:
            self.processor.worker.join(max(0, timeout_seconds - (time.monotonic() - started)))
            if self.processor.worker.is_alive():
                self.store.increment("shutdown_timeouts")
                return False
        return True
