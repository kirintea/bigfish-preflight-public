from copy import deepcopy

from core.reporting.registry import DOMAINS


def _visible(item, npc):
    return npc in (item.get("visible_to") or [])


def domain_view(world, npc, domain, entity_id=None):
    if npc not in world.npc_ids:
        raise KeyError("not_found")
    if domain not in DOMAINS or not DOMAINS[domain].supported:
        return {"status": "unsupported", "data": None}
    if domain == "events":
        knowledge = set(world.knowledge.get(npc, []))
        events = [deepcopy(world.events[e]) for e in world.knowledge.get(npc, [])]
        for event in events:
            if event.get("source_event_id") not in knowledge:
                event["source_event_id"] = None
        return {"status": "known" if world.knowledge.get(npc) else "unknown",
                "data": events, "revision": world.revision}
    if domain == "conversation":
        conversations = []
        for cid, state in world.domain_states.get(domain, {}).items():
            if entity_id is not None and cid != entity_id:
                continue
            messages = [deepcopy(m) for m in world.messages.values() if m["conversation_id"] == cid and
                        (npc == m["author"] or npc in m["actual_recipients"])]
            if npc in (state["data"].get("members") or []) or messages:
                conversations.append({"conversation_id": cid, "status": state["data"]["status"], "messages": messages,
                                      "revision": state["revision"], "source": _source(state)})
        return {"status": "known" if conversations else "unknown", "data": conversations}
    entity = npc if DOMAINS[domain].entity == "npc" else world.world_id
    state = world.domain_states.get(domain, {}).get(entity)
    if state is None:
        return {"status": "unknown", "data": None}
    data = deepcopy(state["data"])
    if domain == "social":
        known_events = set(world.knowledge.get(npc, []))
        for opinion in data["opinions"] or []:
            if opinion["basis_event_ids"] is not None:
                opinion["basis_event_ids"] = [e for e in opinion["basis_event_ids"] if e in known_events]
    filtered_collections = {
        "environment": ["positions", "locations"], "resources": ["items"],
        "groups": ["groups"], "production": ["orders", "facilities", "crops"],
    }
    for collection in filtered_collections.get(domain, []):
        if data[collection] is not None:
            data[collection] = [item for item in data[collection] if _visible(item, npc)]
    return {"status": "known", "data": data, "revision": state["revision"], "source": _source(state),
            "unknown_fields": [k for k, v in data.items() if v is None]}


def _source(state):
    return {key: state[key] for key in ("report_id", "source_kind", "source_id", "occurred_at_tick", "observed_at_tick")}


def npc_context(world, npc):
    if npc not in world.npc_ids:
        raise KeyError("not_found")
    domains = {domain: domain_view(world, npc, domain) for domain in DOMAINS}
    return {"view": "npc", "world_id": world.world_id, "run_epoch": world.run_epoch,
            "npc_id": npc, "revision": world.revision, "domains": domains,
            "knowledge": domains["events"]["data"],
            "supported_domains": [d for d, spec in DOMAINS.items() if spec.supported],
            "stages": {"memory": "skipped", "hooks": "skipped", "model": "skipped"}}
