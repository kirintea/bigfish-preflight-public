from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import resolve_principal
from core.game.views import npc_context
from core.tracing.context import current_request, request_scope
from core.hooks.assembler import HookAssembler

router = APIRouter(prefix="/api/v1/worlds/{world_id}")


def formal_world(request, principal, world_id):
    if principal.role != "simulator" or world_id not in principal.world_ids:
        raise HTTPException(403, "forbidden_source")
    try:
        return request.app.state.worlds.read("production", world_id)
    except (KeyError, ValueError):
        raise HTTPException(404) from None


def context_response(request, world, npc_id):
    context = replace(current_request.get(), world_id=world.world_id, run_epoch=world.run_epoch)
    with request_scope(context):
        with request.app.state.tracing.tracer.start_as_current_span("context", record_exception=False, set_status_on_exception=False) as span:
            with request_scope(replace(context, span_id=f"{span.get_span_context().span_id:016x}")):
                try:
                    view = npc_context(world, npc_id)
                except KeyError:
                    request.app.state.events.append(current_request.get(), "view_filter", "rejected", "not_found", revision=world.revision)
                    raise HTTPException(404) from None
                references = dict(npc_id=npc_id, revision=world.revision, test_run_id=world.test_run_id)
                request.app.state.events.append(current_request.get(), "view_filter", "ok", **references)
                hook_data = None
                if hasattr(request.app.state, "hook_registry"):
                    active = {hook_id: item for hook_id, item in world.hook_instances.items() if item.get("enabled") and npc_id in item.get("npc_ids", [])}
                    if active:
                        assembly = HookAssembler(request.app.state.hook_registry).assemble(
                            world_id=world.world_id, npc_id=npc_id, tick=world.tick or 0,
                            event_ids=list(world.events), active_ids=set(active),
                        )
                        hook_data = {"status": "applied", "applied": [x.model_dump(mode="json") for x in assembly.applied],
                                     "skipped": [x.__dict__ for x in assembly.skipped], "trimmed": [x.__dict__ for x in assembly.trimmed],
                                     "dependencies": assembly.dependencies, "prompt": assembly.public_text_for(npc_id)}
                        request.app.state.events.append(current_request.get(), "hooks", "ok", **references,
                                                        hook_ids=list(assembly.dependencies))
                for skipped in (("memory", "hooks", "model") if hook_data is None else ("memory", "model")):
                    request.app.state.events.append(current_request.get(), skipped, "skipped", "unsupported", **references)
    return {**view, **({"hooks": hook_data} if hook_data is not None else {}),
            "request_id": context.request_id, "trace_id": context.trace_id}


@router.get("/npcs/{npc_id}/context")
def context(world_id: str, npc_id: str, request: Request, principal=Depends(resolve_principal)):
    return context_response(request, formal_world(request, principal, world_id), npc_id)
