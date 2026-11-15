from state_helpers import run_report


def new_run(client):
    run = client.post('/api/test/v1/runs', json={'name': 'scenario'}).json()
    return run, '/api/test/v1/runs/' + run['test_run_id']


def test_export_import_replay_isolated_and_reset_expires_old_reports(client):
    run, path = new_run(client)
    data = run_report(run, 'needs', {'hunger': 0.8})
    assert client.post(path + '/reports', json=data).status_code == 200
    exported = client.post(path + '/scenario/export').json()
    assert exported['schema_version'] == 1
    assert exported['steps'][0]['payload']['hunger'] == 0.8
    assert 'run_epoch' not in str(exported)
    imported = client.post(path + '/scenario/import', json=exported)
    assert imported.status_code == 200
    original_revision = client.get(path + '/state').json()['revision']
    replay = client.post(path + '/replay', json=exported).json()
    assert replay['completed_steps'] == 1
    assert replay['test_run_id'] != run['test_run_id']
    assert client.get(path + '/state').json()['revision'] == original_revision
    from uuid import uuid4
    reset = client.post(path + '/reset', json=dict(command_id=uuid4().hex,
        run_epoch=run['run_epoch'], expected_revision=original_revision)).json()
    assert reset['run_epoch'] != run['run_epoch']
    stale = client.post(path + '/reports', json=data)
    assert stale.json()['reason'] == 'stale_epoch'


def test_scenario_rejects_unknown_versions_and_stops_invalid_step(client):
    _, path = new_run(client)
    scenario = dict(schema_version=2, content_version=1, name='bad', seed=7,
                    npc_templates=['npc-a'], steps=[])
    assert client.post(path + '/scenario/import', json=scenario).status_code == 422
    scenario.update(schema_version=1, steps=[
        dict(domain='needs', entity_id='npc-a', tick=0, payload={'hunger': 0.2}),
        dict(domain='needs', entity_id='npc-a', tick=1, payload={'hunger': 9}),
        dict(domain='needs', entity_id='npc-a', tick=2, payload={'hunger': 0.4})])
    replay = client.post(path + '/replay', json=scenario).json()
    assert replay['completed_steps'] == 1
    assert replay['failed_step'] == 1
    state = client.get('/api/test/v1/runs/' + replay['test_run_id'] + '/state').json()
    assert state['domain_states']['needs']['npc-a']['data']['hunger'] == 0.2


def test_incremental_replay_advances_one_step_and_deduplicates(client):
    from uuid import uuid4
    _, path = new_run(client)
    scenario = dict(schema_version=1, content_version=1, name='steps', seed=7,
        npc_templates=['npc-a'], steps=[dict(domain='needs', entity_id='npc-a', tick=i,
            payload={'hunger': value}) for i, value in enumerate([0.2, 0.4])])
    started = client.post(path + '/replay/start', json=scenario)
    assert started.status_code == 200
    progress = started.json()
    target = '/api/test/v1/runs/' + progress['test_run_id']
    assert progress['completed_steps'] == 0
    body = dict(command_id=uuid4().hex, run_epoch=progress['run_epoch'], expected_revision=progress['revision'])
    step = client.post(target + '/replay/step', json=body)
    assert step.status_code == 200
    assert step.json()['completed_steps'] == 1
    assert client.post(target + '/replay/step', json=body).json()['completed_steps'] == 1
    assert client.get(target + '/state').json()['domain_states']['needs']['npc-a']['data']['hunger'] == 0.2

