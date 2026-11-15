from fastapi import APIRouter, Request

from core.tracing.context import current_request
from core.tracing.decorators import stage

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    with stage(request.app.state.tracing, request.app.state.events, "health"):
        context = current_request.get()
        return {"status": "ok", "version": request.app.state.config.service_version,
                "request_id": context.request_id, "trace_id": context.trace_id}
