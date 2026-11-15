from secrets import token_urlsafe
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from core.testing import beach
from core.testing.commands import Command, execute, reset_scoped
from core.agent.turns import ModelTurnError, TurnRequest
from core.reporting.schemas import Identifier, StrictModel

router = APIRouter(prefix='/api/play/v1')

class AgentTurnBody(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    request_id: Identifier | None = None
    turn_id: Identifier | None = None
    allow_fallback: bool = True


def same_origin(request: Request):
    # Browser requests are proxied through the same origin; reject cross-site writes.
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'cross_site')
    origin = request.headers.get('origin')
    if origin and origin.split('://')[-1] != request.headers.get('host'):
        raise HTTPException(403, 'cross_site')


def session(request: Request):
    same_origin(request)
    key = request.cookies.get('bigfish_play', '')
    entry = request.app.state.play_sessions.get(key)
    if not entry or entry['expires'] < monotonic():
        raise HTTPException(401, 'session_required')
    return request.app.state.test_runs.get(entry['run_id'])


@router.post('/sessions', status_code=201, dependencies=[Depends(same_origin)])
def create_session(request: Request, response: Response):
    sessions = request.app.state.play_sessions
    for key in list(sessions):
        if sessions[key]['expires'] < monotonic():
            del sessions[key]
    if len(sessions) >= 128:
        raise HTTPException(429, 'session_capacity')
    world = request.app.state.test_runs.create('Beach prologue', ['npc-bigfish', 'npc-claude'])
    world = request.app.state.worlds.reset('test', world.world_id, uuid4().hex, prologue=beach.initial(), initialize=beach.sync_domains)
    key = token_urlsafe(32)
    sessions[key] = dict(run_id=world.test_run_id, expires=monotonic()+8*3600)
    response.set_cookie('bigfish_play', key, httponly=True, samesite='strict', max_age=8*3600, path='/api/play')
    return beach.view(world)


@router.get('/state')
def state(world=Depends(session)):
    return beach.view(world)


@router.post('/command')
def command(body: beach.PlayCommand, request: Request, world=Depends(session)):
    return execute(request.app.state.worlds, world.world_id, body, lambda w: beach.apply(w, body),
        operation='beach:' + body.kind, view_on_duplicate=beach.view, transient=body.kind in {'tick', 'deliver'})

@router.post('/agent-turn')
async def agent_turn(body: AgentTurnBody, request: Request, world=Depends(session)):
    target = world.prologue.get('dialogue')
    if not target or target not in world.npc_ids:
        raise HTTPException(422, 'dialogue_required')
    turn = TurnRequest(request_id=body.request_id or uuid4().hex,
                       conversation_id='beach-dialogue', turn_id=body.turn_id or uuid4().hex,
                       speaker_id='player', trigger='player_message', text=body.text,
                       allow_fallback=body.allow_fallback)
    try:
        result = await request.app.state.turns.submit_async(world.world_id, turn, npc_id=target)
    except ModelTurnError as exc:
        raise HTTPException(502, exc.error_code) from exc
    def mutate(candidate):
        state = candidate.prologue
        if any(message.get('agent_request_id') == turn.request_id
               for message in state['messages']):
            return None, False
        conversation = dict(members=['player', target], messages=state['messages'])
        player_msg = beach.append(conversation, 'player', body.text, [target], None)
        agent_msg = beach.append(conversation, target, result.utterance, ['player'], player_msg['message_id'])
        agent_msg['adapter'] = 'agent-turn'
        agent_msg['agent_request_id'] = turn.request_id
        state['messages'] = conversation['messages']
        state['model'] = 'offline-agent' if request.app.state.config.offline_mode else 'llm-agent'
        if state['checkpoint'] == 'encounter':
            state['checkpoint'] = 'gathering'
        beach.sync_domains(candidate, revision=candidate.revision + 1)
        candidate.revision += 1
        return None, True
    request.app.state.worlds.transact('test', world.world_id, mutate)
    return beach.view(request.app.state.worlds.read('test', world.world_id))


@router.post('/reset')
def reset(body: Command, request: Request, world=Depends(session)):
    return beach.view(reset_scoped(request.app.state.worlds, world.world_id, body,
        prologue=beach.initial(), initialize=beach.sync_domains))
