from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from api.test_control import get_run
from core.auth import require_admin
from core.memory.compression import CompressionService
from core.memory.retrieval import MemoryIndex
from core.memory.schemas import MemoryEntry
from core.memory.writer import MemoryWriter
from core.reporting.schemas import Identifier, StrictModel
from core.tracing.context import current_request

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


class WriteBody(StrictModel):
    source_event_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    content: str = Field(min_length=1, max_length=4096)
    acquisition: str = "direct"


class CompressBody(StrictModel):
    memory_ids: list[Identifier] = Field(min_length=1, max_length=128)


def _out(request, data):
    context = current_request.get()
    return data | {"request_id": context.request_id, "trace_id": context.trace_id}


@router.get("/{test_run_id}/npcs/{npc_id}/memory")
def search(test_run_id: str, npc_id: str, request: Request, query: str = ""):
    world = get_run(request, test_run_id)
    if npc_id not in world.npc_ids:
        raise HTTPException(404, "not_found")
    entries = world.npc_memories.get(npc_id, [])
    result = MemoryIndex(entries).search(world_id=world.world_id, npc_id=npc_id, query=query,
                                        valid_sources=set(world.events))
    return _out(request, {"items": [item.as_dict() for item in result.items], "excluded": result.excluded})


@router.post("/{test_run_id}/npcs/{npc_id}/memory", status_code=201)
def write(test_run_id: str, npc_id: str, body: WriteBody, request: Request):
    world = get_run(request, test_run_id)
    if npc_id not in world.npc_ids:
        raise HTTPException(404, "not_found")
    try:
        entry = MemoryWriter().write(world.model_dump(mode="json"), owner_npc_id=npc_id,
            source_event_ids=body.source_event_ids, content=body.content, acquisition=body.acquisition,
            occurred_at_tick=world.tick, observed_at_tick=world.tick)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload = entry.as_dict()
    def mutate(candidate):
        items = candidate.npc_memories.setdefault(npc_id, [])
        if not any(item["memory_id"] == payload["memory_id"] for item in items):
            items.append(payload); candidate.revision += 1
            return payload, True
        return items[0], False
    saved = request.app.state.worlds.transact("test", world.world_id, mutate)
    return _out(request, saved)


@router.post("/{test_run_id}/npcs/{npc_id}/memory/compress")
def compress(test_run_id: str, npc_id: str, body: CompressBody, request: Request):
    world = get_run(request, test_run_id)
    entries = [entry for entry in world.npc_memories.get(npc_id, []) if entry["memory_id"] in body.memory_ids]
    if len(entries) != len(body.memory_ids):
        raise HTTPException(404, "memory_not_found")
    candidate = CompressionService().build_candidate(entries, target_version=max((entry.get("compression_version") or 0) for entry in entries) + 1)
    if not CompressionService().validate(candidate, valid_sources=set(world.events)):
        raise HTTPException(409, "memory_sources_invalid")
    return _out(request, {"candidate": asdict(candidate), "status": "candidate"})
