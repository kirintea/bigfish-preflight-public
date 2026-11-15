import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone

from pydantic import ValidationError

from core.tracing.context import current_request, request_scope
from .registry import DOMAINS
from .schemas import Batch, REPORT_ADAPTER


class Rejection(Exception):
    def __init__(self, reason, revision=None):
        self.reason, self.revision = reason, revision


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def outcome(reason="none", *, report_id=None, revision=None, event_ids=None, status=None, errors=None):
    context = current_request.get()
    if status is None:
        status = {"none": "accepted", "revision_conflict": "conflict", "id_collision": "conflict",
                  "stale_epoch": "expired"}.get(reason, "rejected")
    return dict(status=status, reason=reason, report_id=report_id,
                request_id=context.request_id if context else "internal",
                trace_id=context.trace_id if context else "0" * 32,
                revision=revision, event_ids=event_ids or [], errors=errors or [])


class ReportingService:
    def __init__(self, repository, events=None, tracing=None):
        self.repository, self.events, self.tracing = repository, events, tracing

    def submit(self, source, data):
        return self._submit(source, data, batch=False)

    def submit_batch(self, source, data):
        return self._submit(source, data, batch=True)

    def _submit(self, source, data, *, batch):
        try:
            parsed = Batch.model_validate(data) if batch else REPORT_ADAPTER.validate_python(data)
        except ValidationError as exc:
            self._record("report_validate", "rejected", "invalid_payload")
            return outcome("invalid_payload", errors=[".".join(map(str, e["loc"])) for e in exc.errors()])
        reports = parsed.reports if batch else [parsed]
        first = reports[0]
        identifier = parsed.batch_id if batch else first.report_id
        context = current_request.get()
        if context is not None:
            context = replace(context, world_id=first.world_id, run_epoch=first.run_epoch)
        def execute():
            self._record("report_validate", "started", report_id=identifier)
            try:
                if any(not source.permits(r) for r in reports):
                    raise Rejection("forbidden_source")
                if any(r.world_id != first.world_id or r.run_epoch != first.run_epoch for r in reports):
                    raise Rejection("invalid_payload")
                result = self.repository.transact(source.namespace, first.world_id,
                    lambda world: self._apply(world, reports, parsed if batch else None))
            except Rejection as exc:
                result = outcome(exc.reason, report_id=identifier, revision=exc.revision)
            except KeyError:
                result = outcome("not_found", report_id=identifier)
            except OSError:
                result = outcome("storage_error", report_id=identifier)
            self._record("report_validate", "ok" if result["status"] in {"accepted", "duplicate"} else "rejected",
                         result["reason"], report_id=identifier, revision=result["revision"],
                         test_run_id=source.source_id if source.kind == "test" else None)
            self._record("report_commit", "ok" if result["status"] == "accepted" else "skipped",
                         "duplicate" if result["status"] == "duplicate" else result["reason"], report_id=identifier,
                         revision=result["revision"], test_run_id=source.source_id if source.kind == "test" else None)
            return result
        if context is None:
            return execute()
        with request_scope(context):
            if self.tracing is None:
                return execute()
            with self.tracing.tracer.start_as_current_span("report", record_exception=False, set_status_on_exception=False) as span:
                with request_scope(replace(context, span_id=f"{span.get_span_context().span_id:016x}")):
                    return execute()

    def _record(self, stage, status, reason="none", **references):
        context = current_request.get()
        if self.events is not None and context is not None:
            self.events.append(context, stage, status, reason, **references)

    def _apply(self, world, reports, batch):
        first = reports[0]
        identifier = batch.batch_id if batch else first.report_id
        def reject(reason):
            raise Rejection(reason, world.revision)
        if first.run_epoch != world.run_epoch:
            reject("stale_epoch")
        digest = fingerprint((batch if batch else first).model_dump(mode="json", exclude_unset=True))
        receipts = world.batch_receipts if batch else world.report_receipts
        if identifier in receipts:
            receipt = receipts[identifier]
            if receipt["fingerprint"] != digest:
                reject("id_collision")
            return outcome(report_id=identifier, revision=receipt["revision"], event_ids=receipt["event_ids"], status="duplicate"), False
        expected = batch.expected_revision if batch else first.expected_revision
        if expected != world.revision:
            reject("revision_conflict")
        if any(r.expected_revision != expected for r in reports):
            reject("invalid_payload")
        if len({r.report_id for r in reports}) != len(reports):
            reject("id_collision")
        event_ids = []
        existing_events, existing_messages = set(world.events), set(world.messages)
        for report in reports:
            if report.report_id in world.report_receipts:
                reject("id_collision")
            if not DOMAINS[report.domain].supported:
                reject("unsupported_domain")
            entity = DOMAINS[report.domain].entity
            if entity == "world" and report.entity_id != world.world_id:
                reject("invalid_payload")
            if entity == "npc" and report.entity_id not in world.npc_ids:
                reject("invalid_payload")
            sequence_key = json.dumps([report.source_kind, report.source_id, report.domain, report.entity_id])
            if report.sequence != world.source_sequences.get(sequence_key, 0) + 1:
                reject("sequence_gap")
            states = world.domain_states.setdefault(report.domain, {})
            previous = states.get(report.entity_id)
            if report.mode == "delta" and previous is None:
                reject("missing_baseline")
            if previous and report.domain != "events" and report.occurred_at_tick < previous["occurred_at_tick"]:
                reject("invalid_payload")
            payload = report.payload.model_dump(mode="json")
            if report.mode == "delta":
                payload = previous["data"] | report.payload.model_dump(mode="json", exclude_unset=True)
                try:
                    payload = DOMAINS[report.domain].schema.model_validate(payload).model_dump(mode="json")
                except ValidationError:
                    reject("invalid_payload")
            if report.domain == "world":
                self._clock(world, payload, reject)
            states[report.entity_id] = dict(data=payload, revision=world.revision + 1,
                report_id=report.report_id, source_kind=report.source_kind, source_id=report.source_id,
                occurred_at_tick=report.occurred_at_tick, observed_at_tick=report.observed_at_tick,
                received_at=datetime.now(timezone.utc).isoformat())
            world.source_sequences[sequence_key] = report.sequence
            if report.domain == "events":
                for event in payload["events"] or []:
                    record = dict(event)
                    record["occurred_at_tick"] = event["occurred_at_tick"] if event["occurred_at_tick"] is not None else report.occurred_at_tick
                    record["observed_at_tick"] = event["observed_at_tick"] if event["observed_at_tick"] is not None else report.observed_at_tick
                    if record["observed_at_tick"] < record["occurred_at_tick"] or record["observed_at_tick"] > report.observed_at_tick:
                        reject("invalid_payload")
                    record.update(source_kind=report.source_kind, source_id=report.source_id)
                    event_id = event["event_id"]
                    if event_id in world.events and world.events[event_id] != record:
                        reject("id_collision")
                    world.events[event_id] = record
                    if event_id not in event_ids:
                        event_ids.append(event_id)
                    for npc in set(event["observers"] + event["actual_recipients"]):
                        knowledge = world.knowledge.setdefault(npc, [])
                        if event_id not in knowledge:
                            knowledge.append(event_id)
            if report.domain == "conversation":
                for message in payload["messages"] or []:
                    record = dict(message, conversation_id=report.entity_id, source_kind=report.source_kind, source_id=report.source_id)
                    mid = message["message_id"]
                    if mid in world.messages:
                        original = {k: v for k, v in world.messages[mid].items() if k != "members_at_delivery"}
                        if original != record:
                            reject("id_collision")
                    else:
                        members = set(payload.get("members") or [])
                        if not {message["author"], *message["actual_recipients"], *message["targets"]} <= members:
                            reject("invalid_payload")
                        world.messages[mid] = dict(record, members_at_delivery=sorted(members))
        self._validate_references(world, existing_events, existing_messages, reject)
        world.revision += 1
        if world.test_run_id:
            for report in reports:
                world.scenario_steps.append(dict(domain=report.domain,
                    entity_id=report.entity_id if DOMAINS[report.domain].entity != "world" else "$world",
                    tick=report.occurred_at_tick, mode=report.mode,
                    payload=report.payload.model_dump(mode="json", exclude_unset=True)))
        for report in reports:
            own_events = [e.event_id for e in report.payload.events or []] if report.domain == "events" else []
            world.report_receipts[report.report_id] = dict(fingerprint=fingerprint(report.model_dump(mode="json", exclude_unset=True)),
                                                          revision=world.revision, event_ids=own_events)
        if batch:
            world.batch_receipts[identifier] = dict(fingerprint=digest, revision=world.revision, event_ids=event_ids)
        return outcome(report_id=identifier, revision=world.revision, event_ids=event_ids), True

    @staticmethod
    def _clock(world, payload, reject):
        tick = payload.get("tick")
        if tick is not None:
            if world.tick is not None and tick < world.tick:
                reject("invalid_payload")
            if world.pause_reasons and world.tick is not None and tick > world.tick:
                reject("paused")
            world.tick = tick
        if payload.get("pause_reasons") is not None:
            world.pause_reasons = set(payload["pause_reasons"])
        payload["tick"] = world.tick
        payload["pause_reasons"] = sorted(world.pause_reasons)

    @staticmethod
    def _validate_references(world, existing_events, existing_messages, reject):
        npcs = set(world.npc_ids)
        def ids(domain, collection, key):
            return {item[key] for state in world.domain_states.get(domain, {}).values() for item in state["data"].get(collection) or []}
        locations = ids("environment", "locations", "location_id")
        items = ids("resources", "items", "item_id")
        orders = ids("production", "orders", "order_id")
        npc_single = {"npc_id", "owner_id", "holder_id", "actor", "author"}
        npc_lists = {"targets", "observers", "actual_recipients", "visible_to", "members"}
        def validate(value):
            if isinstance(value, list):
                for item in value:
                    validate(item)
                return
            if not isinstance(value, dict):
                return
            for key, item in value.items():
                if item is None:
                    continue
                if key in npc_single and item not in npcs:
                    reject("invalid_payload")
                if key in npc_lists and (len(item) != len(set(item)) or not set(item) <= npcs):
                    reject("invalid_payload")
                if key == "roles" and not set(item) <= set(value.get("members") or []):
                    reject("invalid_payload")
                if key == "location_id" and item not in locations:
                    reject("invalid_payload")
                if key == "basis_event_ids" and not set(item) <= world.events.keys():
                    reject("invalid_payload")
                if key == "source_event_id" and item not in world.events:
                    reject("invalid_payload")
                if key == "target_id":
                    targets = {"npc": npcs, "item": items, "location": locations, "order": orders}
                    target_set = npcs if "value" in value or "relationship" in value else targets.get(value.get("target_kind"), set())
                    if item not in target_set:
                        reject("invalid_payload")
                if isinstance(item, list) and item and isinstance(item[0], dict):
                    identifier_keys = [k for k in item[0] if k.endswith("_id") and k not in {"npc_id", "target_id", "owner_id", "holder_id", "location_id", "source_event_id"}]
                    if identifier_keys:
                        collection_ids = [entry[identifier_keys[0]] for entry in item]
                        if len(collection_ids) != len(set(collection_ids)):
                            reject("invalid_payload")
                validate(item)
        # Current state references must remain valid; history keeps its original identity.
        for domain, states in world.domain_states.items():
            for state in states.values():
                if domain == "events":
                    continue
                validate({k: v for k, v in state["data"].items() if k != "messages"})
        for event_id in world.events.keys() - existing_events:
            validate(world.events[event_id])
        for message_id in world.messages.keys() - existing_messages:
            validate(world.messages[message_id])
