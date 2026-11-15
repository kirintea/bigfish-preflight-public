from copy import deepcopy
from uuid import uuid4
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from core.testing.commands import Command
from core.reporting.schemas import Identifier

INTERACTION_MODES = {"disabled", "automatic", "forced"}


class MembersCommand(Command):
    members: list[Identifier] = Field(min_length=1, max_length=16)
    interaction_mode: Literal['disabled', 'automatic', 'forced'] = 'disabled'


class MessageCommand(Command):
    text: str = Field(min_length=1, max_length=2000)
    targets: list[Identifier] = Field(default_factory=list, max_length=16)
    reply_to: Identifier | None = None
    generate: bool = False


def validate_members(world, members, *, creating=False):
    if len(set(members)) != len(members) or not set(members) <= {'player', *world.npc_ids}:
        raise HTTPException(422, 'invalid_members')
    if creating and len(members) < 2:
        raise HTTPException(422, 'minimum_members')


def validate_interaction_mode(mode):
    if mode not in INTERACTION_MODES:
        raise HTTPException(422, 'invalid_interaction_mode')


def create(world, body):
    validate_members(world, body.members, creating=True)
    validate_interaction_mode(body.interaction_mode)
    cid = uuid4().hex
    chat = dict(conversation_id=cid, members=body.members, status='open', messages=[],
                mode='formal', scheduler='bounded', adapter='offline-script', member_revision=1,
                interaction_mode=body.interaction_mode)
    world.chat_sessions[cid] = chat
    return deepcopy(chat)


def get(world, cid):
    if cid not in world.chat_sessions:
        raise HTTPException(404, 'not_found')
    return world.chat_sessions[cid]


def view(world, cid):
    return dict(deepcopy(get(world, cid)), revision=world.revision, run_epoch=world.run_epoch)


def members(world, cid, body):
    validate_members(world, body.members)
    validate_interaction_mode(body.interaction_mode)
    chat = get(world, cid)
    chat.update(members=body.members, status='open' if len(body.members) >= 2 else 'paused',
                member_revision=chat['member_revision'] + 1,
                interaction_mode=body.interaction_mode)
    return deepcopy(chat)


def message(world, cid, body):
    chat = get(world, cid)
    if 'player' not in chat['members']:
        raise HTTPException(403, 'observer_read_only')
    if chat['status'] != 'open' or not body.text.strip():
        raise HTTPException(422, 'conversation_paused_or_empty')
    if not set(body.targets) <= set(chat['members']):
        raise HTTPException(422, 'invalid_target')
    if body.reply_to and body.reply_to not in {m['message_id'] for m in chat['messages']}:
        raise HTTPException(422, 'unknown_reply')
    if len(chat['messages']) > 2000:
        raise HTTPException(409, 'conversation_capacity')
    player_message = append(chat, 'player', body.text, body.targets, body.reply_to)
    if body.generate:
        npc_ids = [member for member in chat['members'] if member != 'player']
        if body.targets:
            npc_ids = [n for n in npc_ids if n in body.targets]
        return dict(deepcopy(chat), generation_targets=npc_ids)
    # Script responses exercise the legacy offline delivery chain.
    for npc in chat['members']:
        if npc == 'player':
            continue
        text = ('嗯，我听见了。先找点吃的吧，海边的浆果看起来不错。' if npc == 'npc-bigfish'
                else '先观察四周。漂流木收好，之后会用得上。')
        append(chat, npc, text, ['player'], player_message['message_id'])
    return deepcopy(chat)


def append(chat, author, text, targets=None, reply_to=None):
    msg = dict(message_id=uuid4().hex, author=author, text=text, targets=targets or [],
        actual_recipients=[m for m in chat['members'] if m != author],
        members_at_delivery=list(chat['members']), reply_to=reply_to,
        adapter='player' if author == 'player' else 'offline-script')
    chat['messages'].append(msg)
    return msg


def context(world, cid, viewer):
    if viewer not in {'player', *world.npc_ids}:
        raise HTTPException(404, 'not_found')
    chat = get(world, cid)
    messages = [m for m in chat['messages'] if m['author'] == viewer or viewer in m['actual_recipients']]
    return dict(viewer=viewer, conversation_id=cid, messages=messages,
        revision=world.revision, scheduler=chat.get('scheduler', 'available'),
        interaction_mode=chat.get('interaction_mode', 'disabled'))
