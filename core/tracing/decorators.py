"""Tracing helpers and structured local diagnostic stages."""

import time
from contextlib import contextmanager

from opentelemetry.trace import Status, StatusCode

from .context import current_request
from .metrics import STAGES


def create_span(tracer, name, attributes=None):
    return tracer.start_as_current_span(
        name, attributes=attributes or {}, record_exception=False, set_status_on_exception=False
    )


@contextmanager
def stage(tracing, store, name, *, skipped=False):
    context = current_request.get()
    if context is None:
        raise RuntimeError("Stage requires request context")
    name = name if name in STAGES else "other"
    started = time.monotonic()
    with create_span(tracing.tracer, name) as span:
        span_id = f"{span.get_span_context().span_id:016x}"
        store.append(context, name, "started", span_id=span_id)
        try:
            yield span
        except BaseException:
            span.set_status(Status(StatusCode.ERROR))
            store.append(context, name, "error", "internal_error", (time.monotonic() - started) * 1000, span_id)
            raise
        else:
            store.append(context, name, "skipped" if skipped else "ok", "unsupported" if skipped else "none",
                         (time.monotonic() - started) * 1000, span_id)
