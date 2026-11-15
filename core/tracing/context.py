from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from opentelemetry.context import Context


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    trace_id: str
    span_id: str
    world_id: str | None = None
    run_epoch: str | int | None = None
    parent_context: Context | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_span(cls, request_id, span, **references):
        context = span.get_span_context()
        return cls(request_id, f"{context.trace_id:032x}", f"{context.span_id:016x}", **references)


current_request: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


@contextmanager
def request_scope(context):
    token = current_request.set(context)
    try:
        yield context
    finally:
        current_request.reset(token)
