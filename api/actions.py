from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from api.test_control import get_run
from core.auth import require_admin
from core.reporting.schemas import Identifier, StrictModel

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


class ActionBody(StrictModel):
    capability: Identifier
    parameters: dict = Field(default_factory=dict)
    action_id: Identifier | None = None


@router.post("/{test_run_id}/npcs/{npc_id}/actions")
def submit_action(test_run_id: str, npc_id: str, body: ActionBody, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.submit(world.world_id, npc_id, body.capability,
                                               body.parameters, action_id=body.action_id)
    return result.model_dump(mode="json")


@router.get("/{test_run_id}/actions/{action_id}")
def get_action(test_run_id: str, action_id: str, request: Request):
    get_run(request, test_run_id)
    result = request.app.state.actions.get(action_id)
    if result is None:
        raise HTTPException(404, "not_found")
    return result.model_dump(mode="json")
