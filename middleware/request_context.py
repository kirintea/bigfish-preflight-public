import time
from uuid import uuid4

from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.responses import JSONResponse

from core.tracing.context import RequestContext, request_scope


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app
        self.propagator = TraceContextTextMapPropagator()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        state = scope["app"].state
        tracing, store = state.tracing, state.events
        # Retain parent IDs while excluding arbitrary vendor state and baggage.
        carrier = {"traceparent": value.decode("ascii") for key, value in scope["headers"]
                   if key == b"traceparent" and value.isascii()}
        started = time.monotonic()
        status_code, response_started = 500, False
        parent_context = self.propagator.extract(carrier)
        with tracing.tracer.start_as_current_span(
            "request", context=parent_context, kind=SpanKind.SERVER,
            record_exception=False, set_status_on_exception=False,
        ) as span:
            context = RequestContext.from_span(uuid4().hex, span, parent_context=parent_context)
            with request_scope(context):
                store.append(context, "request", "started")

                async def correlated_send(message):
                    nonlocal status_code, response_started
                    if message["type"] == "http.response.start":
                        status_code, response_started = message["status"], True
                        headers = {"x-request-id": context.request_id, "x-trace-id": context.trace_id}
                        self.propagator.inject(headers)
                        message = dict(message)
                        replaced = {key.encode() for key in headers}
                        message["headers"] = [(key, value) for key, value in message.get("headers", []) if key not in replaced]
                        message["headers"].extend((key.encode(), value.encode()) for key, value in headers.items())
                    await send(message)

                try:
                    await self.app(scope, receive, correlated_send)
                except Exception:
                    status_code = 500
                    if not response_started:
                        response = JSONResponse({"detail": "internal_error", "request_id": context.request_id,
                                                 "trace_id": context.trace_id}, status_code=500)
                        await response(scope, receive, correlated_send)
                    else:
                        raise
                finally:
                    status = "error" if status_code >= 500 else "rejected" if status_code >= 400 else "ok"
                    reason = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(
                        status_code, "internal_error" if status_code >= 500 else "none")
                    if status_code >= 500:
                        span.set_status(Status(StatusCode.ERROR))
                    store.append(context, "request", status, reason, (time.monotonic() - started) * 1000)
                    if status_code >= 500:
                        state.log.event("request_failed", context.request_id,
                                        status_code=status_code, trace_id=context.trace_id)
