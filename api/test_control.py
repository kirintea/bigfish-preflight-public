from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from api.context import context_response
from api.reports import REPORT_ERRORS, report_response
from core.auth import require_admin
from core.reporting.schemas import Batch, Report, ReportResult, StrictModel
from core.testing.adapter import test_source
from core.tracing.context import current_request
from core.reporting.schemas import Identifier
from core.testing import scenarios, chat, beach
from core.testing.commands import Command, execute, reset_scoped
from uuid import uuid4
from core.reporting.registry import DOMAINS
from core.game.repository import safe_id

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


@router.get('/schema')
def schemas():
    return {name: dict(schema=domain.schema.model_json_schema(), entity=domain.entity,
                       supported=domain.supported) for name, domain in DOMAINS.items()}


class NewRun(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    npc_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=32)


def get_run(request, run_id):
    try:
        return request.app.state.test_runs.get(run_id)
    except (KeyError, ValueError):
        raise HTTPException(404) from None


@router.post("", status_code=201)
def create_run(body: NewRun, request: Request):
    if body.npc_ids and len(body.npc_ids) != len(set(body.npc_ids)):
        raise HTTPException(422)
    world = request.app.state.test_runs.create(body.name, body.npc_ids)
    context = current_request.get()
    return {key: getattr(world, key) for key in ("test_run_id", "world_id", "run_epoch", "revision")} | {
        "request_id": context.request_id, "trace_id": context.trace_id}


@router.get("/{test_run_id}/state")
def state(test_run_id: str, request: Request):
    world = get_run(request, test_run_id)
    context = current_request.get()
    return {**world.model_dump(mode="json"), "view": "management", "request_id": context.request_id, "trace_id": context.trace_id}


@router.post("/{test_run_id}/reports", response_model=ReportResult, responses=REPORT_ERRORS)
def reports(test_run_id: str, body: Report, request: Request):
    source = test_source(get_run(request, test_run_id))
    return report_response(request.app.state.reporting.submit(source, body.model_dump(mode="json", exclude_unset=True)))


@router.post("/{test_run_id}/reports/batch", response_model=ReportResult, responses=REPORT_ERRORS)
def batch_reports(test_run_id: str, body: Batch, request: Request):
    source = test_source(get_run(request, test_run_id))
    return report_response(request.app.state.reporting.submit_batch(source, body.model_dump(mode="json", exclude_unset=True)))


@router.get("/{test_run_id}/npcs/{npc_id}/context")
def context(test_run_id: str, npc_id: str, request: Request):
    return context_response(request, get_run(request, test_run_id), npc_id)


@router.post('/{test_run_id}/scenario/export')
def export_scenario(test_run_id: str, request: Request):
    return scenarios.export(get_run(request, test_run_id))


@router.post('/{test_run_id}/scenario/import')
def import_scenario(test_run_id: str, body: scenarios.Scenario, request: Request):
    world = get_run(request, test_run_id)
    data = body.model_dump(mode='json')
    def save(candidate):
        candidate.saved_scenarios[body.name] = data
        candidate.revision += 1
        return data, True
    return request.app.state.worlds.transact('test', world.world_id, save)


@router.post('/{test_run_id}/reset')
def reset(test_run_id: str, body: Command, request: Request):
    world = get_run(request, test_run_id)
    return reset_scoped(request.app.state.worlds, world.world_id, body).model_dump(mode='json')


@router.post('/{test_run_id}/replay')
def replay(test_run_id: str, body: scenarios.Scenario, request: Request):
    get_run(request, test_run_id)
    return scenarios.replay(request.app.state, body)


@router.post('/{test_run_id}/replay/start')
def start_replay(test_run_id: str, body: scenarios.Scenario, request: Request):
    get_run(request, test_run_id)
    return scenarios.start_replay(request.app.state, body)


@router.post('/{test_run_id}/replay/step')
def replay_step(test_run_id: str, body: Command, request: Request):
    return scenarios.replay_step(request.app.state, get_run(request, test_run_id).world_id, body)


@router.post('/{test_run_id}/conversations', status_code=201)
def create_conversation(test_run_id: str, body: chat.MembersCommand, request: Request):
    world = get_run(request, test_run_id)
    result = execute(request.app.state.worlds, world.world_id, body, lambda w: chat.create(w, body), operation='chat:create')
    result['model'] = 'llm-agent' if not request.app.state.config.offline_mode else 'offline-agent'
    return result


@router.get('/{test_run_id}/conversations/{conversation_id}')
def get_conversation(test_run_id: str, conversation_id: str, request: Request):
    world = get_run(request, test_run_id)
    return dict(chat.get(world, conversation_id), revision=world.revision, run_epoch=world.run_epoch,
                model='llm-agent' if not request.app.state.config.offline_mode else 'offline-agent')


@router.post('/{test_run_id}/conversations/{conversation_id}/members')
def change_members(test_run_id: str, conversation_id: str, body: chat.MembersCommand, request: Request):
    world = get_run(request, test_run_id)
    return execute(request.app.state.worlds, world.world_id, body, lambda w: chat.members(w, conversation_id, body), operation='chat:members:' + conversation_id, view_on_duplicate=lambda w: chat.view(w, conversation_id))


@router.post('/{test_run_id}/conversations/{conversation_id}/messages')
def send_message(test_run_id: str, conversation_id: str, body: chat.MessageCommand, request: Request):
    world = get_run(request, test_run_id)
    return execute(request.app.state.worlds, world.world_id, body, lambda w: chat.message(w, conversation_id, body), operation='chat:message:' + conversation_id, view_on_duplicate=lambda w: chat.view(w, conversation_id))


@router.get('/{test_run_id}/conversations/{conversation_id}/context/{viewer}')
def conversation_context(test_run_id: str, conversation_id: str, viewer: str, request: Request):
    return chat.context(get_run(request, test_run_id), conversation_id, viewer)


class PresetCommand(Command):
    preset: beach.Preset


@router.post('/{test_run_id}/prologue/preset')
def prologue_preset(test_run_id: str, body: PresetCommand, request: Request):
    world = get_run(request, test_run_id)
    state = beach.preset_state(body.preset)
    return beach.view(reset_scoped(request.app.state.worlds, world.world_id, body, prologue=state, initialize=beach.sync_domains))


@router.post('/{test_run_id}/prologue/step')
def prologue_step(test_run_id: str, body: beach.PlayCommand, request: Request):
    world = get_run(request, test_run_id)
    def step(candidate):
        if not candidate.prologue:
            raise HTTPException(404)
        beach.advance(candidate.prologue)
        beach.sync_domains(candidate, revision=candidate.revision+1)
        return beach.view(candidate)
    return execute(request.app.state.worlds, world.world_id, body, step, operation='beach:step', view_on_duplicate=beach.view)


@router.get('/{test_run_id}/prologue/presets')
def list_beach_presets(test_run_id: str, request: Request):
    return get_run(request, test_run_id).beach_presets


@router.post('/{test_run_id}/prologue/presets/{preset_id}')
def save_beach_preset(test_run_id: str, preset_id: str, body: PresetCommand, request: Request):
    world = get_run(request, test_run_id)
    try:
        safe_id(preset_id)
    except ValueError:
        raise HTTPException(422) from None
    beach.preset_state(body.preset)
    def save(candidate):
        if len(candidate.beach_presets) >= 32 and preset_id not in candidate.beach_presets:
            raise HTTPException(409, 'preset_capacity')
        candidate.beach_presets[preset_id] = body.preset.model_dump(mode='json')
        return beach.view(candidate)
    return execute(request.app.state.worlds, world.world_id, body, save, operation='beach:save:' + preset_id, view_on_duplicate=beach.view)


@router.post('/{test_run_id}/prologue/presets/{preset_id}/load')
def load_beach_preset(test_run_id: str, preset_id: str, body: Command, request: Request):
    world = get_run(request, test_run_id)
    if preset_id not in world.beach_presets:
        raise HTTPException(404)
    state = beach.preset_state(beach.Preset.model_validate(world.beach_presets[preset_id]))
    return beach.view(reset_scoped(request.app.state.worlds, world.world_id, body,
        prologue=state, initialize=beach.sync_domains))
