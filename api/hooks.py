from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from core.auth import require_admin
from core.reporting.schemas import Identifier, StrictModel
from core.tracing.context import current_request
from core.hooks.assembler import HookAssembler

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


class ActivateHook(StrictModel):
    event_id: Identifier
    npc_ids: list[Identifier] | None = Field(default=None, max_length=32)


def _run(request, test_run_id):
    try:
        return request.app.state.test_runs.get(test_run_id)
    except (KeyError, ValueError):
        raise HTTPException(404) from None


def _response(request, **data):
    context = current_request.get()
    return data | {"request_id": context.request_id, "trace_id": context.trace_id}


@router.get("/{test_run_id}/hooks")
def list_hooks(test_run_id: str, request: Request):
    world = _run(request, test_run_id)
    hooks = []
    for item in request.app.state.hook_registry.items():
        hooks.append(item.definition.model_dump(mode="json") | {
            "active": item.definition.hook_id in world.hook_instances,
            "instance": world.hook_instances.get(item.definition.hook_id),
        })
    return _response(request, hooks=hooks, revision=world.revision, run_epoch=world.run_epoch)


@router.get("/{test_run_id}/hooks/active")
def active_hooks(test_run_id: str, request: Request):
    world = _run(request, test_run_id)
    return _response(request, hooks=world.hook_instances, revision=world.revision, run_epoch=world.run_epoch)


@router.get("/{test_run_id}/hooks/preview/{npc_id}")
def preview_hooks(test_run_id: str, npc_id: str, request: Request):
    world = _run(request, test_run_id)
    if npc_id not in world.npc_ids:
        raise HTTPException(404, "not_found")
    active = {hook_id: item for hook_id, item in world.hook_instances.items() if item.get("enabled")}
    allowed = {hook_id for hook_id, item in active.items() if npc_id in item.get("npc_ids", [])}
    assembly = HookAssembler(request.app.state.hook_registry).assemble(
        world_id=world.world_id, npc_id=npc_id, tick=world.tick or 0,
        event_ids=list(world.events), active_ids=allowed,
    )
    return _response(request, npc_id=npc_id, applied=[x.model_dump(mode="json") for x in assembly.applied],
                     skipped=[x.__dict__ for x in assembly.skipped], trimmed=[x.__dict__ for x in assembly.trimmed],
                     dependencies=assembly.dependencies, prompt=assembly.public_text_for(npc_id))


@router.post("/{test_run_id}/hooks/{hook_id}/activate")
def activate_hook(test_run_id: str, hook_id: str, body: ActivateHook, request: Request):
    world = _run(request, test_run_id)
    registered = request.app.state.hook_registry.get(hook_id)
    if registered is None:
        raise HTTPException(404, "hook_not_registered")
    if body.event_id not in world.events:
        raise HTTPException(404, "event_not_found")
    npc_ids = body.npc_ids or world.npc_ids
    if any(npc not in world.npc_ids for npc in npc_ids) or len(npc_ids) != len(set(npc_ids)):
        raise HTTPException(422, "invalid_npc_scope")
    if registered.definition.world_scope and world.world_id not in registered.definition.world_scope:
        raise HTTPException(409, "hook_wrong_world")
    instance = {"hook_id": hook_id, "version": registered.definition.version,
                "event_id": body.event_id, "npc_ids": npc_ids, "enabled": True,
                "activated_at_tick": world.tick or 0}

    def mutate(candidate):
        candidate.hook_instances[hook_id] = instance
        candidate.revision += 1
        return instance, True

    saved = request.app.state.worlds.transact("test", world.world_id, mutate)
    return _response(request, status="active", **saved)


@router.post("/{test_run_id}/hooks/{hook_id}/deactivate")
def deactivate_hook(test_run_id: str, hook_id: str, request: Request):
    world = _run(request, test_run_id)
    if request.app.state.hook_registry.get(hook_id) is None:
        raise HTTPException(404, "hook_not_registered")
    if hook_id not in world.hook_instances:
        raise HTTPException(404, "hook_not_active")

    def mutate(candidate):
        instance = candidate.hook_instances.pop(hook_id)
        candidate.revision += 1
        return instance, True

    instance = request.app.state.worlds.transact("test", world.world_id, mutate)
    return _response(request, status="revoked", **instance)
