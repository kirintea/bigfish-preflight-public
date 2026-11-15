from fastapi import APIRouter, Depends, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST

from core.auth import require_admin
from core.tracing.context import current_request
from core.tracing.decorators import stage

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/api/v1/observe/requests/{request_id}")
async def request_stages(request_id: str, request: Request):
    with stage(request.app.state.tracing, request.app.state.events, "observe"):
        result = request.app.state.events.get(request_id)
        if result is None:
            raise HTTPException(404, "not_found")
        return result


@router.get("/api/v1/observe/status")
async def observation_status(request: Request):
    with stage(request.app.state.tracing, request.app.state.events, "observe"):
        context = current_request.get()
        return {**request.app.state.events.status(), "request_id": context.request_id, "trace_id": context.trace_id}


@router.get("/metrics")
async def metrics(request: Request):
    with stage(request.app.state.tracing, request.app.state.events, "metrics"):
        return Response(request.app.state.events.metrics.render(), media_type=CONTENT_TYPE_LATEST)
