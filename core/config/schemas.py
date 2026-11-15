"""Application settings and validation for file storage, models, and tracing."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

OfflineModelMode = Literal[
    "valid_reply", "invalid_json", "wrong_speaker", "illegal_intent", "timeout",
]


class LLMConfig(BaseModel):
    """LLM model settings for the NPC generation path."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    provider: str = "openai"
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    model: str = "offline-script"
    stream: bool = False
    context_size: int = Field(default=128000, ge=1)
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0, le=2)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    workers: int = Field(default=1, ge=1)
    storage_backend: Literal["file"] = "file"
    storage_dir: Path = Path("runtime")
    test_control_enabled: bool = False
    offline_mode: bool = True
    llm: LLMConfig = Field(default_factory=LLMConfig)
    # Server-side test switch for offline generation branches; player
    # messages can never select or change this mode.
    offline_model_mode: OfflineModelMode = "valid_reply"
    local_observation_enabled: Literal[True] = True
    test_admin_token: SecretStr = SecretStr("")
    simulator_token: SecretStr = SecretStr("")
    simulator_world_ids: frozenset[str] = frozenset()
    simulator_source_ids: frozenset[str] = frozenset()
    simulator_domains: frozenset[str] = frozenset({
        "world", "body", "needs", "social", "activity", "environment", "resources",
        "groups", "production", "events", "conversation",
    })
    otel_enabled: bool = True
    otlp_enabled: bool = False
    otlp_endpoint: str = "http://127.0.0.1:4317"
    otlp_headers: dict[str, SecretStr] = Field(default_factory=dict)
    service_name: str = "bigfish-agent"
    service_version: str = "0.1.0"
    trace_sample_ratio: float = Field(default=1, ge=0, le=1)
    observation_capacity: int = Field(default=4096, ge=4)
    journal_max_bytes: int = Field(default=2_000_000, ge=1024)
    journal_backups: int = Field(default=2, ge=1, le=10)
    export_queue_capacity: int = Field(default=2048, ge=1)
    shutdown_timeout_seconds: float = Field(default=2, gt=0, le=30)

    @model_validator(mode="after")
    def validate_boundaries(self):
        from core.reporting.registry import DOMAINS
        if not self.simulator_domains <= DOMAINS.keys():
            raise ValueError("Unknown simulator domain")
        if self.environment == "production" and self.test_control_enabled:
            raise ValueError("Production cannot enable test control")
        if self.workers != 1:
            raise ValueError("File storage requires exactly one worker")
        admin = self.test_admin_token.get_secret_value()
        simulator = self.simulator_token.get_secret_value()
        if admin and admin == simulator:
            raise ValueError("Management and simulator credentials must differ")
        if self.otlp_enabled and not self.otel_enabled:
            raise ValueError("OTLP requires tracing enabled")
        return self
