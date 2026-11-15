from uuid import uuid4


def setup_chat(client, members=None):
    run = client.post('/api/test/v1/runs', json={'name': 'chat',
        'npc_ids': ['npc-bigfish', 'npc-claude']}).json()
    path = '/api/test/v1/runs/' + run['test_run_id']
    body = dict(run_epoch=run['run_epoch'], expected_revision=0, command_id=uuid4().hex,
                members=members or ['player', 'npc-bigfish', 'npc-claude'])
    response = client.post(path + '/conversations', json=body)
    assert response.status_code == 201
    return path, response.json()


def test_free_text_has_real_author_recipients_and_idempotency(client):
    path, chat = setup_chat(client)
    body = dict(command_id=uuid4().hex, run_epoch=chat['run_epoch'],
        expected_revision=chat['revision'], text='今天海风里有柠檬的味道。', targets=['npc-bigfish'])
    endpoint = path + '/conversations/' + chat['conversation_id'] + '/messages'
    result = client.post(endpoint, json=body)
    assert result.status_code == 200
    messages = result.json()['messages']
    assert messages[0]['text'] == body['text']
    assert messages[0]['author'] == 'player'
    assert messages[0]['actual_recipients'] == ['npc-bigfish', 'npc-claude']
    assert len(messages) == 3
    assert messages[1]['adapter'] == 'offline-script'
    assert client.post(endpoint, json=body).json()['revision'] == result.json()['revision']
    assert len(client.get(path + '/state').json()['chat_sessions'][chat['conversation_id']]['messages']) == 3
    assert client.post(endpoint, json={**body, 'command_id': uuid4().hex, 'author': 'npc-bigfish'}).status_code == 422


def test_membership_conflicts_observer_and_minimum_members(client):
    path, chat = setup_chat(client, ['npc-bigfish', 'npc-claude'])
    endpoint = path + '/conversations/' + chat['conversation_id']
    body = dict(command_id=uuid4().hex, run_epoch=chat['run_epoch'], expected_revision=chat['revision'], text='hello')
    assert client.post(endpoint + '/messages', json=body).status_code == 403
    changed = client.post(endpoint + '/members', json={k: v for k, v in body.items() if k != 'text'} | {
        'members': ['player', 'npc-bigfish']})
    assert changed.status_code == 200
    assert client.post(endpoint + '/messages', json=body).status_code == 409
    latest = changed.json()
    paused = client.post(endpoint + '/members', json=dict(command_id=uuid4().hex,
        run_epoch=latest['run_epoch'], expected_revision=latest['revision'], members=['npc-bigfish'])).json()
    assert paused['status'] == 'paused'
    assert paused['scheduler'] == 'bounded'


def test_group_agent_turns_can_reply_for_each_npc(client):
    path, chat = setup_chat(client)
    message = client.post(path + '/conversations/' + chat['conversation_id'] + '/messages', json={
        'command_id': uuid4().hex, 'run_epoch': chat['run_epoch'],
        'expected_revision': chat['revision'], 'text': 'hello', 'generate': True,
    })
    assert message.status_code == 200
    for npc_id in ('npc-bigfish', 'npc-claude'):
        turn = client.post(path + '/conversations/' + chat['conversation_id'] + '/turns', json={
            'turn_id': 'turn-' + npc_id, 'request_id': 'request-' + npc_id,
            'text': 'hello', 'npc_id': npc_id,
        })
        assert turn.status_code == 202
    latest = client.get(path + '/conversations/' + chat['conversation_id']).json()
    assert {m['author'] for m in latest['messages']} == {'player', 'npc-bigfish', 'npc-claude'}
