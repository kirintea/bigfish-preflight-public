from fastapi import APIRouter, Depends, HTTPException, Request

from api.context import context_response, formal_world
from core.auth import resolve_principal
from core.reporting.registry import DOMAINS

router = APIRouter(prefix="/api/v1/worlds/{world_id}")


def read_domain(request, world, npc_id, domain):
    if domain not in DOMAINS:
        raise HTTPException(404)
    view = context_response(request, world, npc_id)
    return {**view["domains"][domain], **{k: view[k] for k in ("world_id", "run_epoch", "npc_id", "request_id", "trace_id")},
            "world_revision": world.revision}


@router.get("/state/{domain}")
def state(world_id: str, domain: str, npc_id: str, request: Request, principal=Depends(resolve_principal)):
    if domain not in {"world", "environment", "resources", "groups", "production", "hooks"}:
        raise HTTPException(404)
    return read_domain(request, formal_world(request, principal, world_id), npc_id, domain)


@router.get("/npcs/{npc_id}/state/{domain}")
def npc_state(world_id: str, npc_id: str, domain: str, request: Request, principal=Depends(resolve_principal)):
    if domain not in {"body", "needs", "social", "activity"}:
        raise HTTPException(404)
    return read_domain(request, formal_world(request, principal, world_id), npc_id, domain)


@router.get("/npcs/{npc_id}/knowledge")
def knowledge(world_id: str, npc_id: str, request: Request, principal=Depends(resolve_principal)):
    return read_domain(request, formal_world(request, principal, world_id), npc_id, "events")


@router.get("/conversations/{conversation_id}")
def conversation(world_id: str, conversation_id: str, npc_id: str, request: Request, principal=Depends(resolve_principal)):
    result = read_domain(request, formal_world(request, principal, world_id), npc_id, "conversation")
    result["data"] = [item for item in result["data"] if item["conversation_id"] == conversation_id]
    if not result["data"]:
        raise HTTPException(404)
    return result


@router.get("/actions/{action_id}")
def action(world_id: str, action_id: str, npc_id: str, request: Request, principal=Depends(resolve_principal)):
    return read_domain(request, formal_world(request, principal, world_id), npc_id, "action_result")
