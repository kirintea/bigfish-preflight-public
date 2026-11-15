import json
from collections import Counter, deque
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .context import RequestContext
from .metrics import Metrics, REASONS, STAGES, STATUSES


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(max_length=128)
    trace_id: str
    span_id: str
    stage: str
    status: Literal["started", "ok", "error", "rejected", "skipped", "other"]
    reason: str
    duration_ms: float = Field(ge=0)
    world_id: str | None = Field(default=None, max_length=128)
    run_epoch: str | int | None = None
    report_id: str | None = Field(default=None, max_length=128)
    event_id: str | None = Field(default=None, max_length=128)
    turn_id: str | None = Field(default=None, max_length=128)
    action_id: str | None = Field(default=None, max_length=128)
    test_run_id: str | None = Field(default=None, max_length=128)
    npc_id: str | None = Field(default=None, max_length=128)
    revision: int | None = Field(default=None, ge=0)


class EventStore:
    """Bounded diagnostic ring and rotating journal; not a business transaction log."""

    def __init__(self, config):
        self.config = config
        self.lock = RLock()
        self.records = deque(maxlen=config.observation_capacity)
        self.counters = Counter()
        self.metrics = Metrics()
        self.directory = Path(config.storage_dir) / "observe"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.journal = self.directory / "stages.jsonl"
        # Opening the required sink fails startup immediately if storage is unavailable.
        with self.journal.open("ab"):
            pass

    def increment(self, name, amount=1):
        with self.lock:
            self.counters[name] += amount

    def append(self, context: RequestContext, stage, status, reason="none", duration_ms=0, span_id=None, **references):
        record = StageRecord(
            request_id=context.request_id, trace_id=context.trace_id,
            span_id=span_id or context.span_id, world_id=context.world_id, run_epoch=context.run_epoch,
            stage=stage if stage in STAGES else "other",
            status=status if status in STATUSES else "other",
            reason=reason if reason in REASONS else "other",
            duration_ms=duration_ms, **references,
        )
        data = record.model_dump()
        encoded = (json.dumps(data, separators=(",", ":")) + "\n").encode()
        with self.lock:
            if len(self.records) == self.records.maxlen:
                self.counters["dropped_records"] += 1
            self.records.append(data)
            self.metrics.record(record.stage, record.status, record.reason, duration_ms)
            if record.status not in {"error", "rejected"}:
                return
            try:
                if len(encoded) > self.config.journal_max_bytes:
                    self.counters["journal_dropped"] += 1
                    return
                if self.journal.stat().st_size + len(encoded) > self.config.journal_max_bytes:
                    self._rotate()
                with self.journal.open("ab") as stream:
                    stream.write(encoded)
            except OSError:
                self.counters["journal_errors"] += 1

    def _rotate(self):
        for index in range(self.config.journal_backups, 0, -1):
            source = self.journal if index == 1 else self.directory / f"stages.{index - 1}.jsonl"
            target = self.directory / f"stages.{index}.jsonl"
            if source.exists():
                source.replace(target)
        self.journal.touch()
        self.counters["rotations"] += 1

    def get(self, request_id):
        with self.lock:
            stages = [dict(record) for record in self.records if record["request_id"] == request_id]
        if not stages:
            return None
        return {"request_id": request_id, "trace_id": stages[0]["trace_id"], "stages": stages}

    def status(self):
        with self.lock:
            result = {name: self.counters[name] for name in (
                "dropped_records", "rotations", "journal_dropped", "journal_errors", "export_errors",
                "export_dropped", "exported_spans", "sampled_out", "shutdown_timeouts", "flush_timeouts",
                "background_shutdown_timeouts",
            )}
            result.update(records=len(self.records), capacity=self.records.maxlen,
                          otel_enabled=self.config.otel_enabled,
                          exporter_enabled=self.config.otlp_enabled,
                          sample_ratio=self.config.trace_sample_ratio,
                          query_scope="current_process", journal_backups=self.config.journal_backups)
            return result

    def save_shutdown_status(self):
        temporary = self.directory / "shutdown-status.tmp"
        try:
            temporary.write_text(json.dumps(self.status(), indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.directory / "shutdown-status.json")
        except OSError:
            self.increment("journal_errors")
