from copy import deepcopy

from fastapi import HTTPException

from core.reporting.schemas import Identifier, StrictModel, Tick
from core.reporting.service import fingerprint


class Command(StrictModel):
    command_id: Identifier
    run_epoch: Identifier
    expected_revision: Tick


def execute(repository, world_id, body, apply, *, operation, view_on_duplicate=None, transient=False):
    digest = fingerprint(dict(operation=operation, body=body.model_dump(mode='json')))

    def mutate(world):
        if body.run_epoch != world.run_epoch:
            raise HTTPException(409, 'stale_epoch')
        receipts = world.transient_receipts if transient else world.command_receipts
        receipt = world.command_receipts.get(body.command_id) or world.transient_receipts.get(body.command_id)
        if receipt:
            if receipt['fingerprint'] != digest:
                raise HTTPException(409, 'id_collision')
            return view_on_duplicate(world) if view_on_duplicate else deepcopy(receipt['response']), False
        if body.expected_revision != world.revision:
            raise HTTPException(409, 'revision_conflict')
        if not transient and len(receipts) >= 20000:
            raise HTTPException(409, 'run_capacity')
        revision = world.revision
        response = apply(world)
        if world.revision == revision:
            world.revision += 1
        elif world.revision != revision + 1:
            raise ValueError('command must commit exactly one revision')
        response.update(revision=world.revision, run_epoch=world.run_epoch)
        receipts[body.command_id] = dict(fingerprint=digest,
            response={} if view_on_duplicate else deepcopy(response))
        if transient and len(receipts) > 64:
            del receipts[next(iter(receipts))]
        return response, True

    return repository.transact('test', world_id, mutate)


def reset_scoped(repository, world_id, body, **kwargs):
    from uuid import uuid4
    from core.game.repository import ResetConflict
    try:
        return repository.reset('test', world_id, uuid4().hex,
            expected_epoch=body.run_epoch, expected_revision=body.expected_revision, **kwargs)
    except ResetConflict as error:
        raise HTTPException(409, str(error)) from None
