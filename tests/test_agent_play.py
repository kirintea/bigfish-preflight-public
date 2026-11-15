def test_prologue_dialogue_uses_agent_turn_service(client):
    created = client.post('/api/play/v1/sessions').json()
    client.cookies.set('bigfish_play', client.cookies.get('bigfish_play'))
    # The play session starts at the encounter checkpoint; open dialogue first.
    opened = client.post('/api/play/v1/command', json={
        'command_id': 'open-agent-dialogue', 'run_epoch': created['run_epoch'],
        'expected_revision': created['revision'], 'kind': 'interact', 'target': 'npc-bigfish',
    })
    assert opened.status_code == 200
    result = client.post('/api/play/v1/agent-turn', json={
        'text': 'hello agent', 'request_id': 'agent-retry-1', 'turn_id': 'agent-retry-1',
    })
    assert result.status_code == 200
    assert result.json()['model'] == 'offline-agent'
    assert any(m['adapter'] == 'agent-turn' for m in result.json()['messages'])
    retry = client.post('/api/play/v1/agent-turn', json={
        'text': 'hello agent', 'request_id': 'agent-retry-1', 'turn_id': 'agent-retry-1',
    })
    assert retry.status_code == 200
    assert len(retry.json()['messages']) == len(result.json()['messages']) == 2
