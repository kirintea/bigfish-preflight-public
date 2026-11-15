"""Authoritative deterministic beach simulation; coordinates are scene pixels."""
from copy import deepcopy
from math import cos, floor, hypot, sin
from typing import Literal

from fastapi import HTTPException
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder
from pydantic import Field

from core.reporting.schemas import Identifier, StrictModel
from core.reporting.registry import DOMAINS
from core.testing.chat import append
from core.testing.commands import Command

WIDTH, HEIGHT, TILE = 1408, 800, 32
TREES = [(96, 64), (208, 32), (352, 64), (864, 32), (1024, 64), (1184, 32), (1312, 96)]
SOLIDS = [(32, 224, 128, 160), (96, 96, 416, 64), (768, 64, 576, 96),
          (1280, 256, 96, 160), *[(x+20, y+56, 22, 40) for x, y in TREES]]
OBJECTS = {
    'berry-01': dict(x=416, y=288, kind='berry', remaining=3, radius=70),
    'berry-02': dict(x=1088, y=256, kind='berry', remaining=3, radius=70),
    'wood-01': dict(x=256, y=492, kind='wood', remaining=1, radius=60),
    'wood-02': dict(x=1088, y=524, kind='wood', remaining=1, radius=60),
    'shell-01': dict(x=588, y=588, kind='shell', remaining=1, radius=52),
    'crate-01': dict(x=1144, y=376, kind='crate', remaining=1, radius=70),
    'sign-01': dict(x=664, y=192, kind='sign', remaining=1, radius=70),
}
NAMES = {'npc-bigfish': '大肥鱼', 'npc-claude': '克劳德', 'cook': '厨师',
         'merchant': '商人', 'farmer': '农夫', 'adventurer': '冒险家', 'mechanic': '机械师'}


def shore(column):
    return 18 + floor(3 * sin(column / 9))


def walkable(x, y):
    if not (12 <= x < WIDTH-12 and 12 <= y < HEIGHT-12):
        return False
    for px, py in [(x-10, y-7), (x+10, y-7), (x-10, y+7), (x+10, y+7)]:
        col, row = floor(px/TILE), floor(py/TILE)
        if row > shore(col) or row < 3 + floor(1.5*cos(col/6)):
            return False
        if any(sx-1 <= px <= sx+w+1 and sy-1 <= py <= sy+h+1 for sx, sy, w, h in SOLIDS):
            return False
    return True


GRID = [[int(walkable(col*TILE+16, row*TILE+16)) for col in range(44)] for row in range(25)]


def route(start, end):
    grid = Grid(matrix=GRID)
    sx, sy = int(start[0]//TILE), int(start[1]//TILE)
    ex, ey = int(end[0]//TILE), int(end[1]//TILE)
    if not (0 <= ex < 44 and 0 <= ey < 25 and GRID[ey][ex]):
        return []
    path, _ = AStarFinder(max_runs=1500).find_path(grid.node(sx, sy), grid.node(ex, ey), grid)
    return [[node.x*TILE+16, node.y*TILE+16] for node in path][1:]


def actor(template, x, y, personality='mellow'):
    return dict(template=template, name=NAMES.get(template, template), x=x, y=y,
                mode='idle', personality=personality, path=[], goal=None, speech=None, facing='down', hunger=0.35, mood=0.65)


def initial():
    return dict(schema_version=1, seed=7, tick=0, checkpoint='encounter',
        actors={'player': dict(actor('player', 704, 400), name='沈理'),
                'npc-bigfish': actor('npc-bigfish', 768, 400)},
        objects=deepcopy(OBJECTS), inventory=dict(berry=0, wood=0, shell=0),
        pause_reasons=[], dialogue=None, messages=[], last_action=None, model='offline-agent')


def view(world):
    # Only public scene fields cross the player boundary; no management snapshot.
    state = deepcopy(world.prologue)
    return dict(state, revision=world.revision, run_epoch=world.run_epoch,
                test_run_id=world.test_run_id, model=state.get('model', 'offline-rules'))


def sync_domains(world, *, revision=None):
    state = world.prologue
    revision = world.revision if revision is None else revision
    world.npc_ids = list(dict.fromkeys(['player', 'npc-bigfish', 'npc-claude', *state['actors']]))
    world.tick = state['tick']
    world.pause_reasons = set(state['pause_reasons'])
    members = list(state['actors'])
    def store(domain, entity, payload):
        data = DOMAINS[domain].schema.model_validate(payload).model_dump(mode='json')
        world.domain_states.setdefault(domain, {})[entity] = dict(data=data, revision=revision,
            report_id=f"scene-{world.run_epoch}-{state['tick']}", source_kind='test',
            source_id=world.test_run_id, occurred_at_tick=state['tick'], observed_at_tick=state['tick'])
    store('world', world.world_id, dict(tick=state['tick'], speed=1.0,
        pause_reasons=state['pause_reasons'], scene='beach'))
    store('environment', world.world_id, dict(weather='clear', temperature_c=26.0,
        locations=[dict(location_id='beach', blocked=False, visible_to=members)],
        positions=[dict(npc_id=aid, location_id='beach', x_m=float(a['x']/32), y_m=float(a['y']/32),
                        reachable=True, visible_to=members) for aid, a in state['actors'].items()]))
    store('resources', world.world_id, dict(items=[
        dict(item_id='bag-'+kind, quantity=float(count), holder_id='player', owner_id='player',
             location_id='beach', visible_to=members) for kind, count in state['inventory'].items()
    ] + [dict(item_id=key, quantity=float(obj['remaining']), location_id='beach', visible_to=members)
         for key, obj in state['objects'].items() if obj['kind'] in {'wood', 'berry', 'shell'}]))
    for aid, a in state['actors'].items():
        store('body', aid, dict(present=True, awake=True, can_move=True, can_speak=True))
        store('needs', aid, dict(hunger=a.get('hunger', 0.35), mood=a.get('mood', 0.65)))
        store('activity', aid, dict(task_id='beach-gathering' if aid == 'player' else None,
            phase='completed' if aid == 'player' and state['checkpoint'] == 'completed' else 'moving' if a['path'] else 'idle',
            progress=float(min(3,state['inventory']['berry'])+min(2,state['inventory']['wood']))/5 if aid == 'player' else None))
    if state['messages']:
        cid = 'beach-dialogue'
        store('conversation', cid, dict(members=members, status='open' if state['dialogue'] else 'paused'))
        for msg in state['messages']:
            world.messages[msg['message_id']] = dict(msg, conversation_id=cid, source_kind='test', source_id=world.test_run_id)


class PlayCommand(Command):
    kind: Literal['tick', 'walk_to', 'interact', 'say', 'close_dialogue', 'follow', 'stay', 'deliver', 'reply', 'pause', 'step']
    dx: float = Field(default=0, ge=-1, le=1)
    dy: float = Field(default=0, ge=-1, le=1)
    target: Identifier | None = None
    text: str | None = Field(default=None, max_length=2000)
    reply_to: Identifier | None = None
    response_kind: Literal['answer', 'later', 'decline'] = 'answer'
    enabled: bool = False
    x: float | None = Field(default=None, ge=0, le=WIDTH)
    y: float | None = Field(default=None, ge=0, le=HEIGHT)


def distance(a, b):
    return hypot(a['x']-b['x'], a['y']-b['y'])


def move(a, dx, dy, amount):
    length = hypot(dx, dy)
    if not length:
        return
    dx, dy = dx/length*amount, dy/length*amount
    # Swept small steps prevent tunneling even if speeds change in later builds.
    count = max(1, int(amount/3)+1)
    for _ in range(count):
        if walkable(a['x']+dx/count, a['y']):
            a['x'] += dx/count
        if walkable(a['x'], a['y']+dy/count):
            a['y'] += dy/count
    a['facing'] = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')


def near(state, target):
    obj = state['objects'].get(target) or state['actors'].get(target)
    player = state['actors']['player']
    if not obj or distance(player, obj) > obj.get('radius', 90):
        raise HTTPException(409, 'out_of_range')
    # A short interaction ray cannot pass through a cliff or tree.
    for i in range(1, 10):
        if not walkable(player['x']+(obj['x']-player['x'])*i/10,
                        player['y']+(obj['y']-player['y'])*i/10):
            raise HTTPException(409, 'blocked_interaction')
    return obj


def advance(state, dx=0, dy=0):
    state['tick'] += 1
    player = state['actors']['player']
    if dx or dy:
        player['path'] = []
        move(player, dx, dy, 16)
    elif player['path']:
        point = player['path'][0]
        delta = hypot(point[0]-player['x'], point[1]-player['y'])
        move(player, point[0]-player['x'], point[1]-player['y'], min(16, delta))
        if delta <= 16:
            player['path'].pop(0)
    for index, (aid, npc) in enumerate(state['actors'].items()):
        if aid == 'player':
            continue
        speech = npc['speech']
        if speech and speech['delivered_at'] is not None and speech['status'] == 'waiting':
            elapsed = state['tick'] - speech['delivered_at']
            if elapsed >= 100:
                speech['status'] = 'expired'
                if npc['personality'] == 'expectant':
                    npc.update(mode='leaving', goal=[1008, 336], path=[])
                    speech['text'] = '那我先去那边看看。想聊的时候再来找我。'
                else:
                    speech['text'] = '没事，等你忙完再说。'
            elif elapsed >= 65:
                speech['text'] = '你听到我说话了吗？不急，忙完再回我。'
        if npc['mode'] == 'stay':
            continue
        if npc['mode'] == 'follow':
            if distance(npc, player) < 80:
                npc['path'] = []
                if state['tick'] % 90 == 0 and (not speech or speech['status'] != 'waiting'):
                    message = append(dict(members=['player', aid], messages=state['messages']), aid,
                        '这阵海风挺舒服的，你觉得呢？', ['player'])
                    message['actual_recipients'] = []
                    npc['speech'] = dict(id=message['message_id'], text=message['text'],
                        status='waiting', delivered_at=None)
                continue
            goal = [int(player['x']//32)*32+16, int(player['y']//32)*32+16]
        elif npc['mode'] == 'leaving':
            goal = npc['goal']
        else:
            goals = [[848, 336], [944, 432], [720, 464], [560, 368]]
            goal = goals[(state['tick']//80+index+state['seed']) % len(goals)]
        if not npc['path'] or npc['goal'] != goal or state['tick'] % 15 == 0:
            npc['goal'] = goal
            npc['path'] = route((npc['x'], npc['y']), goal)
        if npc['path']:
            point = npc['path'][0]
            delta = hypot(point[0]-npc['x'], point[1]-npc['y'])
            move(npc, point[0]-npc['x'], point[1]-npc['y'], min(9, delta))
            if delta <= 9:
                npc['path'].pop(0)
        elif npc['mode'] == 'leaving':
            npc['mode'] = 'idle'


def apply(world, body):
    state = world.prologue
    if not state:
        raise HTTPException(404, 'not_found')
    kind = body.kind
    if kind == 'tick':
        if not state['pause_reasons']:
            advance(state, body.dx, body.dy)
    elif kind == 'walk_to':
        if state['pause_reasons'] or body.x is None or body.y is None or not walkable(body.x, body.y):
            raise HTTPException(409, 'unreachable')
        player = state['actors']['player']
        path = route((player['x'], player['y']), (body.x, body.y))
        if not path and distance(player, dict(x=body.x, y=body.y)) > 45:
            raise HTTPException(409, 'unreachable')
        player['path'] = path + [[body.x, body.y]]
    elif kind in {'pause', 'step'}:
        # Player pause is safe; debug single-step uses the separately protected API.
        if kind == 'step':
            raise HTTPException(403, 'debug_only')
        reasons = set(state['pause_reasons'])
        reasons.add('manual') if body.enabled else reasons.discard('manual')
        state['pause_reasons'] = sorted(reasons)
    elif kind == 'close_dialogue':
        state['dialogue'] = None
        state['pause_reasons'] = [r for r in state['pause_reasons'] if r != 'dialogue']
    elif kind == 'interact':
        obj = near(state, body.target)
        if body.target in state['actors']:
            if body.target == 'player':
                raise HTTPException(422, 'invalid_target')
            state['dialogue'] = body.target
            state['actors']['player']['path'] = []
            state['pause_reasons'] = sorted(set(state['pause_reasons']) | {'dialogue'})
            state['last_action'] = 'talk'
        elif obj['kind'] in {'berry', 'wood', 'shell'}:
            if state['checkpoint'] == 'encounter':
                raise HTTPException(409, 'encounter_required')
            if not obj['remaining']:
                raise HTTPException(409, 'depleted')
            state['inventory'][obj['kind']] += obj['remaining']
            obj['remaining'] = 0
            state['last_action'] = 'collected:' + body.target
            event_id = 'collect-' + body.command_id
            witnesses = [aid for aid, a in state['actors'].items() if distance(a, obj) <= 160]
            world.events[event_id] = dict(event_id=event_id, fact=f"player collected {obj['kind']}",
                kind='confirmed', actor='player', targets=[], observers=witnesses,
                actual_recipients=[], source='direct', source_event_id=None,
                occurred_at_tick=state['tick'], observed_at_tick=state['tick'])
            for aid in witnesses:
                world.knowledge.setdefault(aid, []).append(event_id)
            if state['inventory']['berry'] >= 3 and state['inventory']['wood'] >= 2:
                state['checkpoint'] = 'completed'
        elif obj['kind'] == 'crate':
            if obj['remaining'] == 0:
                raise HTTPException(409, 'already_opened')
            obj['remaining'] = 0
            state['last_action'] = '箱子里只有被海水打湿的纸，没有可用物品。'
        else:
            state['last_action'] = '路牌：沿海岸向东。小心潮水，别走进深水。'
    elif kind == 'say':
        target = state['dialogue']
        if not target or not body.text or not body.text.strip():
            raise HTTPException(422, 'dialogue_required')
        if body.reply_to and body.reply_to not in {m['message_id'] for m in state['messages']}:
            raise HTTPException(422, 'unknown_reply')
        conversation = dict(members=['player', target], messages=state['messages'])
        msg = append(conversation, 'player', body.text, [target], body.reply_to)
        append(conversation, target, '醒啦？叫我大肥鱼就好。肚子有点空……一起找些浆果和漂流木吧。',
               ['player'], msg['message_id'])
        if state['checkpoint'] == 'encounter':
            state['checkpoint'] = 'gathering'
    elif kind in {'follow', 'stay'}:
        npc = near(state, body.target)
        if body.target not in state['actors'] or body.target == 'player':
            raise HTTPException(422, 'invalid_target')
        if kind == 'follow' and state['checkpoint'] == 'encounter':
            state['last_action'] = '先聊两句吧，我们还不认识呢。'
        else:
            npc.update(mode='follow' if kind == 'follow' else 'stay', path=[], goal=None, speech=None)
            state['last_action'] = '好，我跟着你。' if kind == 'follow' else '我在这里歇一会儿。'
    elif kind in {'deliver', 'reply'}:
        npc = state['actors'].get(body.target)
        speech = npc.get('speech') if npc else None
        if not speech or speech['id'] != body.reply_to or speech['status'] != 'waiting':
            raise HTTPException(409, 'stale_speech')
        if kind == 'deliver':
            if state['dialogue']:
                raise HTTPException(409, 'speech_not_visible')
            if speech['delivered_at'] is None:
                speech['delivered_at'] = state['tick']
                for message in state['messages']:
                    if message['message_id'] == speech['id']:
                        message['actual_recipients'] = ['player']
        else:
            if not body.text or not body.text.strip():
                raise HTTPException(422, 'empty_message')
            conversation = dict(members=['player', body.target], messages=state['messages'])
            append(conversation, 'player', body.text, [body.target], speech['id'])
            if body.response_kind == 'decline':
                npc.update(mode='leaving', goal=[1008, 336], path=[])
                speech.update(status='declined', text='好，那我先去那边看看。')
            elif body.response_kind == 'later':
                speech.update(status='deferred', text='好，等你忙完。')
            else:
                speech.update(status='answered', text='嗯，我在听。一起慢慢走吧。')
    sync_domains(world, revision=world.revision+1)
    return view(world)


class DebugNPC(StrictModel):
    id: Identifier
    template: Literal['npc-bigfish', 'npc-claude', 'cook', 'merchant', 'farmer', 'adventurer', 'mechanic']
    x: float
    y: float
    personality: Literal['mellow', 'expectant'] = 'mellow'
    mode: Literal['idle', 'follow', 'stay'] = 'idle'
    hunger: float = Field(default=0.35, ge=0, le=1)
    mood: float = Field(default=0.65, ge=0, le=1)


class Preset(StrictModel):
    schema_version: Literal[1] = 1
    seed: int = Field(default=7, ge=0)
    checkpoint: Literal['encounter', 'gathering', 'completed']
    x: float
    y: float
    npcs: list[DebugNPC] = Field(max_length=12)
    collected_objects: list[Identifier] | None = Field(default=None, max_length=7)


def preset_state(body):
    if not walkable(body.x, body.y) or len({n.id for n in body.npcs}) != len(body.npcs):
        raise HTTPException(422, 'invalid_spawn')
    state = initial()
    state.update(seed=body.seed, checkpoint=body.checkpoint)
    state['actors'] = {'player': state['actors']['player']}
    state['actors']['player'].update(x=body.x, y=body.y)
    for npc in body.npcs:
        if npc.id == 'player' or not walkable(npc.x, npc.y):
            raise HTTPException(422, 'invalid_spawn')
        state['actors'][npc.id] = actor(npc.template, npc.x, npc.y, npc.personality)
        state['actors'][npc.id].update(mode=npc.mode, hunger=npc.hunger, mood=npc.mood)
    collected = body.collected_objects
    if collected is None:
        collected = ['berry-01', 'wood-01', 'wood-02'] if body.checkpoint == 'completed' else []
    if len(set(collected)) != len(collected) or any(key not in OBJECTS or OBJECTS[key]['kind'] == 'sign' for key in collected):
        raise HTTPException(422, 'invalid_objects')
    for key in collected:
        obj = state['objects'][key]
        if obj['kind'] in state['inventory']:
            state['inventory'][obj['kind']] += obj['remaining']
        obj['remaining'] = 0
    completed = state['inventory']['berry'] >= 3 and state['inventory']['wood'] >= 2
    if (body.checkpoint == 'completed') != completed or body.checkpoint == 'encounter' and collected:
        raise HTTPException(422, 'checkpoint_inventory_mismatch')
    return state
