import json
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator
from pydantic import ValidationError
from fastapi import HTTPException

from core.reporting.registry import DOMAINS
from core.reporting.schemas import Identifier, StrictModel
from core.testing.adapter import test_source
from core.testing.commands import execute
from core.reporting.schemas import REPORT_ADAPTER
from core.reporting.service import Rejection


class Step(StrictModel):
    domain: str = Field(max_length=32)
    entity_id: str = Field(max_length=96)
    tick: int = Field(ge=0)
    mode: Literal['snapshot', 'delta'] = 'snapshot'
    payload: dict


class Scenario(StrictModel):
    schema_version: Literal[1]
    content_version: Literal[1]
    name: str = Field(min_length=1, max_length=128)
    seed: int = Field(ge=0, le=2**32-1)
    npc_templates: list[Identifier] = Field(min_length=1, max_length=32)
    steps: list[Step] = Field(max_length=1000)

    @model_validator(mode='after')
    def bounded(self):
        if len(set(self.npc_templates)) != len(self.npc_templates) or len(self.model_dump_json().encode()) > 1_000_000:
            raise ValueError('scenario exceeds limits')
        return self


def export(world):
    return Scenario(schema_version=1, content_version=1, name=world.name or 'Scenario', seed=7,
                    npc_templates=world.npc_ids, steps=world.scenario_steps).model_dump(mode='json')


def replay(app, scenario):
    world = app.test_runs.create(scenario.name + ' replay', scenario.npc_templates)
    results = []
    failed = None
    for index, step in enumerate(scenario.steps):
        entity = world.world_id if step.entity_id == '$world' or DOMAINS.get(step.domain, None) and DOMAINS[step.domain].entity == 'world' else step.entity_id
        key = json.dumps(['test', world.test_run_id, step.domain, entity])
        result = app.reporting.submit(test_source(world), dict(schema_version=1,
            report_id=uuid4().hex, request_id=uuid4().hex, world_id=world.world_id,
            run_epoch=world.run_epoch, entity_id=entity, source_kind='test', source_id=world.test_run_id,
            sequence=world.source_sequences.get(key, 0) + 1, expected_revision=world.revision,
            mode=step.mode, occurred_at_tick=step.tick, observed_at_tick=step.tick,
            domain=step.domain, payload=step.payload))
        results.append(dict(step=index, **result))
        if result['status'] != 'accepted':
            failed = index
            break
        world = app.test_runs.get(world.test_run_id)
    return dict(test_run_id=world.test_run_id, run_epoch=world.run_epoch, revision=world.revision,
                completed_steps=len(results) - (failed is not None), failed_step=failed, results=results)


def progress(world):
    replay = world.scenario_replay
    return dict(test_run_id=world.test_run_id, run_epoch=world.run_epoch, revision=world.revision,
        completed_steps=replay.get('cursor', 0), total_steps=len(replay.get('scenario', {}).get('steps', [])),
        results=replay.get('results', []))


def start_replay(app, scenario):
    world = app.test_runs.create(scenario.name + ' step replay', scenario.npc_templates)
    def start(candidate):
        candidate.scenario_replay = dict(scenario=scenario.model_dump(mode='json'), cursor=0, results=[])
        candidate.revision += 1
        return progress(candidate), True
    return app.worlds.transact('test', world.world_id, start)


def replay_step(app, world_id, body):
    def step(world):
        replay = world.scenario_replay
        if not replay or replay['cursor'] >= len(replay['scenario']['steps']):
            raise HTTPException(409, 'replay_complete')
        index = replay['cursor']
        entry = Step.model_validate(replay['scenario']['steps'][index])
        domain = DOMAINS.get(entry.domain)
        entity = world.world_id if entry.entity_id == '$world' or domain and domain.entity == 'world' else entry.entity_id
        key = json.dumps(['test', world.test_run_id, entry.domain, entity])
        data = dict(schema_version=1, report_id=body.command_id, request_id=uuid4().hex,
            world_id=world.world_id, run_epoch=world.run_epoch, entity_id=entity,
            source_kind='test', source_id=world.test_run_id, sequence=world.source_sequences.get(key, 0)+1,
            expected_revision=world.revision, mode=entry.mode, occurred_at_tick=entry.tick,
            observed_at_tick=entry.tick, domain=entry.domain, payload=entry.payload)
        try:
            report = REPORT_ADAPTER.validate_python(data)
            result, _ = app.reporting._apply(world, [report], None)
        except (ValidationError, Rejection):
            raise HTTPException(422, 'invalid_replay_step') from None
        app.reporting._record('report_commit', 'ok', report_id=body.command_id, revision=world.revision)
        replay['cursor'] += 1
        replay['results'].append(dict(step=index, **result))
        return progress(world)
    return execute(app.worlds, world_id, body, step, operation='scenario:step', view_on_duplicate=progress)
