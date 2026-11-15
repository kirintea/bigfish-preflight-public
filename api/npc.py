from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from api.test_control import get_run
from core.auth import require_admin
from core.reporting.schemas import Identifier, StrictModel
from core.game.views import npc_context

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


class NpcCommand(StrictModel):
    capability: Identifier
    parameters: dict = Field(default_factory=dict)
    action_id: Identifier | None = None


@router.get("/{test_run_id}/npcs/{npc_id}/observe")
def observe_npc(test_run_id: str, npc_id: str, request: Request):
    world = get_run(request, test_run_id)
    if npc_id not in world.npc_ids:
        raise HTTPException(404, "not_found")
    return npc_context(world, npc_id)


@router.post("/{test_run_id}/npcs/{npc_id}/commands")
def submit_npc_command(test_run_id: str, npc_id: str, body: NpcCommand, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.submit(world.world_id, npc_id, body.capability,
                                               body.parameters, action_id=body.action_id)
    return result.model_dump(mode="json")


@router.get("/{test_run_id}/npcs/{npc_id}/commands/{action_id}")
def get_npc_command(test_run_id: str, npc_id: str, action_id: str, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.get(action_id)
    if result is None or result.npc_id != npc_id:
        raise HTTPException(404, "not_found")
    return result.model_dump(mode="json")


@router.post("/{test_run_id}/npcs/{npc_id}/commands/{action_id}/cancel")
def cancel_npc_command(test_run_id: str, npc_id: str, action_id: str, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.get(action_id)
    if result is None or result.npc_id != npc_id:
        raise HTTPException(404, "not_found")
    return request.app.state.actions.cancel(world.world_id, action_id).model_dump(mode="json")
