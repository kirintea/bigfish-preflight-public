from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse

from core.auth import resolve_principal
from core.reporting.schemas import Batch, Report, ReportResult
from core.reporting.service import outcome
from core.reporting.sources import simulation_source

REPORT_ERRORS = {code: {"model": ReportResult} for code in (401, 403, 404, 409, 422, 503)}
router = APIRouter(prefix="/api/v1/worlds/{world_id}", responses=REPORT_ERRORS)


def report_response(result):
    code = {"invalid_payload": 422, "forbidden_source": 403, "revision_conflict": 409,
            "sequence_gap": 409, "id_collision": 409, "stale_epoch": 409, "missing_baseline": 409,
            "unsupported_domain": 422, "not_found": 404, "storage_error": 503, "paused": 409}.get(result["reason"], 200)
    return JSONResponse(result, status_code=code)


def submit_formal(request, principal, world_id, report, *, domain=None, entity_id=None):
    source = simulation_source(principal, request.app.state.config, world_id, report.source_id)
    if report.world_id != world_id or (domain is not None and report.domain != domain) or (entity_id is not None and report.entity_id != entity_id):
        return report_response(outcome("invalid_payload", report_id=report.report_id))
    result = request.app.state.reporting.submit(source, report.model_dump(mode="json", exclude_unset=True))
    return report_response(result)


@router.post("/reports/batch", response_model=ReportResult)
def batch_reports(world_id: str, body: Batch, request: Request, principal=Depends(resolve_principal)):
    source = simulation_source(principal, request.app.state.config, world_id, body.reports[0].source_id)
    if any(r.world_id != world_id for r in body.reports):
        return report_response(outcome("invalid_payload", report_id=body.batch_id))
    return report_response(request.app.state.reporting.submit_batch(source, body.model_dump(mode="json", exclude_unset=True)))


@router.post("/reports", response_model=ReportResult)
def reports(world_id: str, body: Report, request: Request, principal=Depends(resolve_principal)):
    return submit_formal(request, principal, world_id, body)


@router.post("/reports/{domain}", response_model=ReportResult)
def world_report(world_id: str, domain: str, body: Report, request: Request, principal=Depends(resolve_principal)):
    if domain in {"body", "needs", "social", "activity", "conversation", "action_result"}:
        raise HTTPException(404)
    return submit_formal(request, principal, world_id, body, domain=domain, entity_id=world_id)


@router.post("/npcs/{npc_id}/reports/{domain}", response_model=ReportResult)
def npc_report(world_id: str, npc_id: str, domain: str, body: Report, request: Request, principal=Depends(resolve_principal)):
    if domain not in {"body", "needs", "social", "activity"}:
        raise HTTPException(404)
    return submit_formal(request, principal, world_id, body, domain=domain, entity_id=npc_id)


@router.post("/conversations/{conversation_id}/reports", response_model=ReportResult)
def conversation_report(world_id: str, conversation_id: str, body: Report, request: Request, principal=Depends(resolve_principal)):
    return submit_formal(request, principal, world_id, body, domain="conversation", entity_id=conversation_id)


@router.post("/actions/{action_id}/reports", response_model=ReportResult)
def action_report(world_id: str, action_id: str, body: Report, request: Request, principal=Depends(resolve_principal)):
    return submit_formal(request, principal, world_id, body, domain="action_result", entity_id=action_id)
