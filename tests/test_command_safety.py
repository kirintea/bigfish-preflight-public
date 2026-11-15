from uuid import uuid4

from test_prologue import start, command
from test_conversation_chat import setup_chat


def scope(state):
    return dict(command_id=uuid4().hex, run_epoch=state['run_epoch'], expected_revision=state['revision'])


def test_transient_ticks_are_bounded_and_evicted_retry_cannot_advance(client):
    state = start(client)
    first = dict(**scope(state), kind='tick')
    state = client.post('/api/play/v1/command', json=first).json()
    for _ in range(70):
        state = command(client, state, 'tick').json()
    stored = client.get('/api/test/v1/runs/' + state['test_run_id'] + '/state').json()
    assert len(stored['command_receipts']) == 0
    assert len(stored['transient_receipts']) <= 64
    assert client.post('/api/play/v1/command', json=first).status_code == 409
    assert client.get('/api/play/v1/state').json()['tick'] == state['tick']


def test_delayed_reset_and_preset_cannot_replace_new_epoch(client):
    state = start(client)
    old = scope(state)
    path = '/api/test/v1/runs/' + state['test_run_id']
    reset = client.post('/api/play/v1/reset', json=old)
    assert reset.status_code == 200
    epoch = reset.json()['run_epoch']
    assert client.post('/api/play/v1/reset', json=old).status_code == 409
    assert client.post(path + '/reset', json=old).status_code == 409
    preset = dict(checkpoint='gathering', x=416, y=304, npcs=[])
    assert client.post(path + '/prologue/preset', json={**old, 'preset': preset}).status_code == 409
    assert client.get('/api/play/v1/state').json()['run_epoch'] == epoch


def test_command_identity_includes_conversation_target(client):
    path, chat = setup_chat(client)
    second = client.post(path + '/conversations', json={**scope(chat), 'members': chat['members']}).json()
    body = dict(**scope(second), text='same command')
    first_path = path + '/conversations/' + chat['conversation_id'] + '/messages'
    second_path = path + '/conversations/' + second['conversation_id'] + '/messages'
    assert client.post(first_path, json=body).status_code == 200
    assert client.post(second_path, json=body).status_code == 409
    assert client.get(path + '/conversations/' + second['conversation_id']).json()['messages'] == []
