from uuid import uuid4

import pytest


def start(client):
    response = client.post('/api/play/v1/sessions')
    assert response.status_code == 201
    return response.json()


def command(client, state, kind, **args):
    return client.post('/api/play/v1/command', json=dict(command_id=uuid4().hex,
        run_epoch=state['run_epoch'], expected_revision=state['revision'], kind=kind, **args))


def test_player_session_is_scoped_and_cannot_claim_authority(client):
    state = start(client)
    assert 'npc-bigfish' in state['actors']
    client.headers.pop('Authorization')
    assert client.get('/api/test/v1/runs/' + state['test_run_id'] + '/state').status_code == 401
    assert command(client, state, 'teleport', x=400).status_code == 422
    assert client.get('/api/play/v1/state').json()['inventory'] == {'berry': 0, 'wood': 0, 'shell': 0}
    assert 'command_receipts' not in str(state)
    assert 'hidden_identity' not in str(state)


def test_server_movement_normalized_boundaries_and_dialogue_pause(client):
    state = start(client)
    initial = state['actors']['player'].copy()
    moved = command(client, state, 'tick', dx=1, dy=1).json()
    actor = moved['actors']['player']
    assert ((actor['x']-initial['x'])**2+(actor['y']-initial['y'])**2)**0.5 == pytest.approx(16)
    # Stop at the shoreline regardless of the number of movement requests.
    for _ in range(55):
        moved = command(client, moved, 'tick', dx=0, dy=1).json()
    assert moved['actors']['player']['y'] < 700
    assert command(client, moved, 'interact', target='berry-01').status_code == 409


def debug_checkpoint(client, state, **changes):
    body = dict(checkpoint='gathering', x=416, y=304, npcs=[]) | changes
    response = client.post('/api/test/v1/runs/' + state['test_run_id'] + '/prologue/preset', json={**scope(state), 'preset': body})
    assert response.status_code == 200
    return response.json()


def test_collect_atomic_single_use_idempotent_and_reset_expires(client):
    state = debug_checkpoint(client, start(client))
    body = dict(command_id=uuid4().hex, run_epoch=state['run_epoch'], expected_revision=state['revision'],
                kind='interact', target='berry-01')
    one = client.post('/api/play/v1/command', json=body)
    assert one.status_code == 200
    assert one.json()['inventory']['berry'] == 3
    assert one.json()['objects']['berry-01']['remaining'] == 0
    assert client.post('/api/play/v1/command', json=body).json()['inventory']['berry'] == 3
    assert command(client, one.json(), 'interact', target='berry-01').status_code == 409
    reset = client.post('/api/play/v1/reset', json=scope(one.json())).json()
    assert reset['run_epoch'] != state['run_epoch']
    assert client.post('/api/play/v1/command', json=body).status_code == 409
    stored = client.get('/api/test/v1/runs/' + state['test_run_id'] + '/state').json()
    assert stored['prologue']['inventory']['berry'] == 0


def test_free_text_confirmed_and_pause_reasons_independent(client):
    state = start(client)
    # Initial position is within speaking range.
    talking = command(client, state, 'interact', target='npc-bigfish').json()
    assert 'dialogue' in talking['pause_reasons']
    sent = command(client, talking, 'say', text='我想先沿着海岸看看。').json()
    assert sent['messages'][0]['author'] == 'player'
    assert sent['messages'][0]['text'] == '我想先沿着海岸看看。'
    assert sent['messages'][1]['adapter'] == 'offline-script'
    assert sent['checkpoint'] == 'gathering'
    assert sent['inventory']['berry'] == 0
    paused = command(client, sent, 'pause', enabled=True).json()
    closed = command(client, paused, 'close_dialogue').json()
    assert closed['pause_reasons'] == ['manual']
    frozen = command(client, closed, 'tick', dx=1, dy=0).json()
    assert frozen['tick'] == closed['tick']


def test_debug_rejects_blocked_spawn_and_duplicate_npc_ids(client):
    state = start(client)
    path = '/api/test/v1/runs/' + state['test_run_id'] + '/prologue/preset'
    assert client.post(path, json=dict(checkpoint='gathering', x=0, y=0, npcs=[])).status_code == 422
    npc = dict(id='cook-1', template='cook', x=704, y=320, personality='expectant')
    assert client.post(path, json=dict(checkpoint='gathering', x=416, y=304, npcs=[npc, npc])).status_code == 422
    assert client.get('/api/play/v1/state').json()['run_epoch'] == state['run_epoch']


def test_click_navigation_uses_reachable_path_and_stops_at_target(client):
    state = start(client)
    moving = command(client, state, 'walk_to', x=416, y=304)
    assert moving.status_code == 200
    state = moving.json()
    assert state['actors']['player']['path']
    for _ in range(35):
        state = command(client, state, 'tick').json()
    assert abs(state['actors']['player']['x'] - 416) < 40
    assert command(client, state, 'walk_to', x=0, y=790).status_code == 409


def test_unread_speech_does_not_expire_and_delivered_timeout_walks_away():
    from core.testing.beach import initial, advance, walkable
    state = initial()
    npc = state['actors']['npc-bigfish']
    npc.update(mode='follow', personality='expectant', x=760, y=400)
    npc['speech'] = dict(id='speech', text='hello', status='waiting', delivered_at=None)
    for _ in range(120):
        advance(state)
    assert npc['speech']['status'] == 'waiting'
    assert npc['mode'] == 'follow'
    npc['speech']['delivered_at'] = state['tick']
    for _ in range(100):
        advance(state)
    assert npc['speech']['status'] == 'expired'
    assert npc['mode'] == 'leaving'
    origin = npc['x'], npc['y']
    advance(state)
    assert (npc['x'], npc['y']) != origin
    assert walkable(npc['x'], npc['y'])


@pytest.mark.parametrize('order', [('berry-01', 'wood-01', 'wood-02'), ('wood-02', 'wood-01', 'berry-01')])
def test_both_collection_orders_complete_and_optional_inspection_adds_no_loot(client, order):
    from core.testing.beach import apply, initial, PlayCommand
    from core.game.schemas import WorldState
    world = WorldState(world_id='world', run_epoch='epoch', npc_ids=['npc-bigfish'], prologue=initial())
    world.prologue['checkpoint'] = 'gathering'
    for target in [*order, 'crate-01', 'sign-01']:
        obj = world.prologue['objects'][target]
        world.prologue['actors']['player'].update(x=obj['x'], y=obj['y']-20)
        apply(world, PlayCommand(command_id=uuid4().hex, run_epoch='epoch', expected_revision=0, kind='interact', target=target))
    assert world.prologue['checkpoint'] == 'completed'
    assert world.prologue['inventory'] == dict(berry=3, wood=2, shell=0)


def test_scene_confirmations_feed_role_context_and_presets_persist(client):
    state = start(client)
    path = '/api/test/v1/runs/' + state['test_run_id']
    view = client.get(path + '/npcs/npc-bigfish/context').json()
    assert view['domains']['environment']['data']['positions']
    state = debug_checkpoint(client, state)
    preset = dict(schema_version=1, checkpoint='completed', seed=123, x=416, y=304, npcs=[])
    saved = client.post(path + '/prologue/presets/after-gathering', json={**scope(state), 'preset': preset})
    assert saved.status_code == 200
    listing = client.get(path + '/prologue/presets').json()
    assert listing['after-gathering']['seed'] == 123
    loaded = client.post(path + '/prologue/presets/after-gathering/load', json=scope(saved.json())).json()
    assert loaded['run_epoch'] != state['run_epoch']
    assert loaded['inventory']['berry'] == 3
    view = client.get(path + '/npcs/player/context').json()
    items = view['domains']['resources']['data']['items']
    assert next(item for item in items if item['item_id'] == 'bag-berry')['quantity'] == 3


def scope(state):
    return dict(command_id=uuid4().hex, run_epoch=state['run_epoch'], expected_revision=state['revision'])


@pytest.mark.parametrize('response_kind,mode,status', [('answer','follow','answered'), ('later','follow','deferred'), ('decline','leaving','declined')])
def test_follow_reply_has_real_reference_and_explicit_disposition(client, response_kind, mode, status):
    state = debug_checkpoint(client, start(client), npcs=[dict(id='npc-bigfish',template='npc-bigfish',x=460,y=304,mode='follow')])
    for _ in range(90):
        state=command(client,state,'tick').json()
    speech=state['actors']['npc-bigfish']['speech']
    assert speech['id'] in {m['message_id'] for m in state['messages']}
    assert state['messages'][-1]['actual_recipients']==[]
    state=command(client,state,'deliver',target='npc-bigfish',reply_to=speech['id']).json()
    assert state['messages'][-1]['actual_recipients']==['player']
    result=command(client,state,'reply',target='npc-bigfish',reply_to=speech['id'],text='我先忙一下。',response_kind=response_kind)
    assert result.status_code==200
    npc=result.json()['actors']['npc-bigfish']
    assert npc['mode']==mode
    assert npc['speech']['status']==status
    assert result.json()['messages'][-1]['reply_to']==speech['id']


def test_debug_preserves_partial_loot_and_edits_independent_instances(client):
    state=debug_checkpoint(client,start(client))
    state=command(client,state,'interact',target='berry-01').json()
    state=debug_checkpoint(client,state,collected_objects=['berry-01'],npcs=[
        dict(id='cook-1',template='cook',x=600,y=304,personality='expectant',mode='stay',hunger=0.9,mood=0.2),
        dict(id='cook-2',template='cook',x=632,y=304,personality='mellow',mode='idle')])
    assert state['inventory']['berry']==3
    assert state['actors']['cook-1']['mode']=='stay'
    assert set(state['actors']) == {'player', 'cook-1', 'cook-2'}
    stored=client.get('/api/test/v1/runs/'+state['test_run_id']+'/state').json()
    assert stored['domain_states']['needs']['cook-1']['data']['hunger']==0.9
    assert stored['domain_states']['needs']['cook-2']['data']['hunger']==0.35


def test_debug_preset_can_remove_all_npcs(client):
    state = debug_checkpoint(client, start(client), npcs=[])
    assert set(state['actors']) == {'player'}


def test_movement_bounds_every_object_reachable_and_sweep_does_not_tunnel():
    from core.testing.beach import initial, route, walkable, move, OBJECTS
    player = initial()['actors']['player']
    for obj in OBJECTS.values():
        assert route((player['x'], player['y']), (obj['x'], obj['y']-20))
    player.update(x=176, y=288)
    move(player, -1, 0, 500)
    assert player['x'] > 160
    assert walkable(player['x'], player['y'])
