def test_turn_api_returns_terminal_result_and_is_queryable(client):
    run = client.post('/api/test/v1/runs', json={'name': 'single', 'npc_ids': ['npc-a']}).json()
    path = f"/api/test/v1/runs/{run['test_run_id']}/conversations/c1/turns"
    response = client.post(path, json={'turn_id': 't1', 'text': 'hello', 'npc_id': 'npc-a'})
    assert response.status_code == 202
    body = response.json()
    assert body['status'] == 'succeeded'
    fetched = client.get(f"/api/test/v1/runs/{run['test_run_id']}/turns/{body['request_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_action_api_rejects_unknown_location(client):
    run = client.post('/api/test/v1/runs', json={'name': 'single', 'npc_ids': ['npc-a']}).json()
    response = client.post(f"/api/test/v1/runs/{run['test_run_id']}/npcs/npc-a/actions",
                           json={'capability': 'guide_to_location', 'parameters': {'location_id': 'missing'}})
    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'


def test_unified_npc_command_api_supports_query_and_cancel(client):
    run = client.post('/api/test/v1/runs', json={'name': 'commands', 'npc_ids': ['npc-a']}).json()
    base = f"/api/test/v1/runs/{run['test_run_id']}/npcs/npc-a"
    created = client.post(base + '/commands', json={'capability': 'follow', 'parameters': {'target_id': 'player'}})
    assert created.status_code == 200
    action = created.json()
    assert action['status'] == 'accepted'
    queried = client.get(base + f"/commands/{action['action_id']}")
    assert queried.json()['action_id'] == action['action_id']
    cancelled = client.post(base + f"/commands/{action['action_id']}/cancel")
    assert cancelled.json()['status'] == 'cancelled'


def test_observe_and_mcp_facade_routes_are_restricted(client):
    run = client.post('/api/test/v1/runs', json={'name': 'observe', 'npc_ids': ['npc-a']}).json()
    observed = client.get(f"/api/test/v1/runs/{run['test_run_id']}/npcs/npc-a/observe")
    assert observed.status_code == 200
    assert observed.json()['npc_id'] == 'npc-a'
    command = client.post(f"/api/test/v1/mcp/{run['test_run_id']}/submit_npc_command/npc-a",
                          json={'capability': 'say', 'parameters': {'text': 'hello'}})
    assert command.status_code == 200
    action_id = command.json()['action_id']
    fetched = client.get(f"/api/test/v1/mcp/{run['test_run_id']}/get_npc_command/{action_id}")
    assert fetched.json()['action_id'] == action_id
