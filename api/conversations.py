from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from api.test_control import get_run
from core.auth import require_admin
from core.conversation.coordinator import ConversationCoordinator
from core.conversation.schemas import Candidate, Conversation, ConversationMessage, Opportunity
from core.conversation.scheduler import OpportunityScheduler
from core.reporting.schemas import Identifier, StrictModel
from core.tracing.context import current_request

router = APIRouter(prefix="/api/test/v1/runs", dependencies=[Depends(require_admin)])


class CreateBody(StrictModel):
    members: list[Identifier] = Field(min_length=2, max_length=16)
    topic: str | None = Field(default=None, max_length=256)


class OpportunityBody(StrictModel):
    trigger: Identifier
    direct_target: Identifier | None = None


class AdvanceBody(StrictModel):
    trigger: Identifier
    content: str | None = Field(default=None, max_length=2000)


def _result(request, data):
    context = current_request.get()
    return data | {"request_id": context.request_id, "trace_id": context.trace_id}


def _load(world, cid):
    raw = world.npc_conversations.get(cid)
    if raw is None:
        raise HTTPException(404, "not_found")
    conversation = Conversation(conversation_id=raw["conversation_id"], world_id=raw["world_id"], run_epoch=raw["run_epoch"],
        mode=raw["mode"], members=raw["members"], member_revision=raw["member_revision"], topic=raw.get("topic"),
        turn_sequence=raw.get("turn_sequence", 0), message_sequence=raw.get("message_sequence", 0), status=raw.get("status", "open"),
        end_reason=raw.get("end_reason"), pause_reasons=set(raw.get("pause_reasons", [])), knowledge=raw.get("knowledge", {}))
    conversation.messages = [ConversationMessage(**message) for message in raw.get("messages", [])]
    conversation.opportunities = {
        key: Opportunity(opportunity_id=value["opportunity_id"], trigger=value["trigger"],
                         conversation_id=value["conversation_id"], selected_npc_id=value.get("selected_npc_id"),
                         candidates=[Candidate(**candidate) for candidate in value.get("candidates", [])],
                         rules=value.get("rules", {}), random_value=value.get("random_value", 0.0))
        for key, value in raw.get("opportunities", {}).items()
    }
    return conversation


def _save(request, conversation):
    payload = asdict(conversation)
    payload["pause_reasons"] = sorted(conversation.pause_reasons)
    def mutate(candidate):
        candidate.npc_conversations[conversation.conversation_id] = payload
        candidate.revision += 1
        return payload, True
    request.app.state.worlds.transact("test", conversation.world_id, mutate)
    return payload


@router.post("/{test_run_id}/conversations/autonomous", status_code=201)
def create(test_run_id: str, body: CreateBody, request: Request):
    world = get_run(request, test_run_id)
    if len(set(body.members)) != len(body.members) or not set(body.members) <= set(world.npc_ids):
        raise HTTPException(422, "invalid_members")
    conversation = ConversationCoordinator().create(world.world_id, world.run_epoch, body.members, topic=body.topic)
    payload = _save(request, conversation)
    return _result(request, payload)


@router.get("/{test_run_id}/conversations/autonomous/{conversation_id}")
def get(test_run_id: str, conversation_id: str, request: Request):
    world = get_run(request, test_run_id)
    return _result(request, _load(world, conversation_id).__dict__ | {"pause_reasons": sorted(_load(world, conversation_id).pause_reasons)})


@router.post("/{test_run_id}/conversations/autonomous/{conversation_id}/opportunities")
def opportunity(test_run_id: str, conversation_id: str, body: OpportunityBody, request: Request):
    world = get_run(request, test_run_id)
    conversation = _load(world, conversation_id)
    scheduler = OpportunityScheduler(seed=int(world.run_epoch[:8], 16) if len(world.run_epoch) >= 8 else 0)
    item = scheduler.schedule(conversation.conversation_id, body.trigger, conversation.members, direct_target=body.direct_target)
    conversation.opportunities[item.opportunity_id] = item
    _save(request, conversation)
    return _result(request, asdict(item))


@router.post("/{test_run_id}/conversations/autonomous/{conversation_id}/advance")
def advance(test_run_id: str, conversation_id: str, body: AdvanceBody, request: Request):
    world = get_run(request, test_run_id)
    conversation = _load(world, conversation_id)
    scheduler = OpportunityScheduler(seed=0)
    item = conversation.opportunities.get(next((key for key, value in conversation.opportunities.items() if value.trigger == body.trigger), ""))
    if item is None:
        item = scheduler.schedule(conversation.conversation_id, body.trigger, conversation.members)
    if item.selected_npc_id is None:
        raise HTTPException(409, "no_eligible_speaker")
    message = ConversationCoordinator().submit_message(conversation, item.selected_npc_id,
        body.content or f"{item.selected_npc_id} responds to {body.trigger}")
    conversation.opportunities[item.opportunity_id] = item
    _save(request, conversation)
    return _result(request, {"opportunity": asdict(item), "message": asdict(message)})
