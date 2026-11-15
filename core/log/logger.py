"""Service log rotation and lifecycle.

Only structured, allowlisted events are written; no third-party logging bridge.
"""

import logging
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from loguru import logger

EVENTS = frozenset({"request_failed",
                    "agent_model_error", "agent_model_timeout", "agent_output_rejected"})


class ServiceLog:
    def __init__(self, log_dir):
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.instance_id = uuid4().hex
        # Each app owns its filtered sinks; another app may still be running.
        with suppress(ValueError):
            logger.remove(0)
        options = dict(
            level="WARNING",
            filter=lambda record: record["extra"].get("service_instance") == self.instance_id,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            diagnose=False, backtrace=False,
        )
        self.sinks = [
            logger.add(sys.stderr, **options),
            logger.add(directory / "agent-server.log", rotation="1 day", retention="30 days",
                       encoding="utf-8", **options),
        ]
        self.logger = logger.bind(service_instance=self.instance_id)
        # The gRPC exporter may log endpoint details. Its errors are counted locally.
        for name in ("opentelemetry.exporter.otlp.proto.grpc.exporter",
                     "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"):
            logging.getLogger(name).disabled = True

    def event(self, name, request_id=None, **fields):
        if name not in EVENTS:
            raise ValueError("Unknown log event")
        reference = request_id if request_id and len(request_id) == 32 and all(c in "0123456789abcdef" for c in request_id) else "-"
        allowed = {"conversation_id", "turn_id", "world_id", "npc_id", "model",
                   "error_code", "exception_type", "exception_message", "traceback",
                   "status", "duration_ms", "trace_id", "status_code"}
        safe = {key: str(value)[:3000 if key == "traceback" else 500] for key, value in fields.items()
                if key in allowed}
        suffix = " ".join(f"{key}={value}" for key, value in safe.items())
        level = "WARNING" if name == "agent_output_rejected" else "ERROR"
        self.logger.log(level, "{} request_id={}{}", name, reference, (" " + suffix) if suffix else "")

    def close(self):
        for sink in self.sinks:
            logger.remove(sink)
