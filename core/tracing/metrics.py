from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

STAGES = frozenset({"request", "auth", "health", "observe", "metrics", "other",
                    "report_validate", "report_commit", "view_filter", "memory", "hooks", "model"})
STATUSES = frozenset({"started", "ok", "error", "rejected", "skipped", "other"})
REASONS = frozenset({"none", "unauthenticated", "forbidden", "not_found", "internal_error", "unsupported", "other",
                     "invalid_payload", "forbidden_source", "revision_conflict", "sequence_gap", "id_collision",
                     "stale_epoch", "unsupported_domain", "missing_baseline", "storage_error", "paused", "duplicate"})


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        labels = ("stage", "status", "reason")
        self.stages = Counter("agent_stages_total", "Local stage outcomes", labels, registry=self.registry)
        self.duration = Histogram("agent_stage_duration_seconds", "Completed stage duration", labels, registry=self.registry)

    def record(self, stage, status, reason, duration_ms):
        labels = (
            stage if stage in STAGES else "other",
            status if status in STATUSES else "other",
            reason if reason in REASONS else "other",
        )
        self.stages.labels(*labels).inc()
        if status != "started":
            self.duration.labels(*labels).observe(duration_ms / 1000)

    def render(self):
        return generate_latest(self.registry)
