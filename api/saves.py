from fastapi import APIRouter, Depends, HTTPException, Request

from api.test_control import get_run
from core.auth import require_admin
from core.saves.service import SaveService
from core.tracing.context import current_request

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


def _out(request, data):
    context = current_request.get()
    return data | {"request_id": context.request_id, "trace_id": context.trace_id}


@router.post("/{test_run_id}/saves", status_code=201)
def create(test_run_id: str, request: Request):
    world = get_run(request, test_run_id)
    snapshot = request.app.state.saves.create("test", world.world_id)
    return _out(request, snapshot.__dict__ | {"world": None})


@router.get("/{test_run_id}/saves")
def list_saves(test_run_id: str, request: Request):
    world = get_run(request, test_run_id)
    items = []
    for path in sorted(request.app.state.saves.root.glob("*.json")):
        try:
            snapshot = request.app.state.saves.read(path.stem)
        except ValueError:
            continue
        if snapshot.world.get("world_id") == world.world_id:
            items.append({"snapshot_id": snapshot.snapshot_id, "checksum": snapshot.checksum,
                          "source_revision": snapshot.source_revision})
    return _out(request, {"items": items})


@router.get("/{test_run_id}/saves/{snapshot_id}")
def read(test_run_id: str, snapshot_id: str, request: Request):
    world = get_run(request, test_run_id)
    try:
        snapshot = request.app.state.saves.read(snapshot_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if snapshot.world.get("world_id") != world.world_id:
        raise HTTPException(404, "not_found")
    return _out(request, {"snapshot_id": snapshot.snapshot_id, "checksum": snapshot.checksum,
                          "source_revision": snapshot.source_revision, "content_version": "world-state-v1",
                          "world": snapshot.world})


@router.post("/{test_run_id}/saves/{snapshot_id}/restore")
def restore(test_run_id: str, snapshot_id: str, request: Request):
    world = get_run(request, test_run_id)
    try:
        restored = request.app.state.saves.restore("test", world.world_id, snapshot_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Requests from the old epoch may still finish, but their commit paths
    # must observe the new epoch before writing.
    return _out(request, {"status": "restored", "world_id": restored.world_id,
                          "run_epoch": restored.run_epoch, "revision": restored.revision})
