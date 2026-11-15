from fastapi import APIRouter, Depends, Request
from core.auth import require_admin
from core.game.mcp import NpcMcpFacade
from api.test_control import get_run

router = APIRouter(prefix="/api/test/v1/mcp", dependencies=[Depends(require_admin)])

def facade(request: Request):
    return NpcMcpFacade(request.app.state.actions, lambda world_id, npc_id: request.app.state.worlds.read("test", world_id))

@router.get("/{test_run_id}/observe_npc/{npc_id}")
def observe_npc(test_run_id: str, npc_id: str, request: Request):
    world = get_run(request, test_run_id)
    if npc_id not in world.npc_ids:
        return {"status": "rejected", "error_code": "unknown_npc"}
    from core.game.views import npc_context
    return npc_context(world, npc_id)

@router.post("/{test_run_id}/submit_npc_command/{npc_id}")
def submit_npc_command(test_run_id: str, npc_id: str, body: dict, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.submit(world.world_id, npc_id, body.get("capability", ""), body.get("parameters", {}), action_id=body.get("action_id"))
    return result.model_dump(mode="json")

@router.get("/{test_run_id}/get_npc_command/{action_id}")
def get_npc_command(test_run_id: str, action_id: str, request: Request):
    get_run(request, test_run_id)
    result = request.app.state.actions.get(action_id)
    return result.model_dump(mode="json") if result else {"status": "not_found"}

@router.post("/{test_run_id}/cancel_npc_command/{action_id}")
def cancel_npc_command(test_run_id: str, action_id: str, request: Request):
    world = get_run(request, test_run_id)
    result = request.app.state.actions.cancel(world.world_id, action_id)
    return result.model_dump(mode="json") if result else {"status": "not_found"}
