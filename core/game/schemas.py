from pydantic import BaseModel, ConfigDict, Field

from core.reporting.schemas import Identifier, PauseReason


class WorldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    world_id: Identifier
    run_epoch: Identifier
    revision: int = Field(default=0, ge=0)
    npc_ids: list[Identifier]
    test_run_id: Identifier | None = None
    name: str | None = None
    tick: int | None = None
    pause_reasons: set[PauseReason] = Field(default_factory=set)
    domain_states: dict[str, dict[str, dict]] = Field(default_factory=dict)
    events: dict[str, dict] = Field(default_factory=dict)
    knowledge: dict[str, list[str]] = Field(default_factory=dict)
    messages: dict[str, dict] = Field(default_factory=dict)
    report_receipts: dict[str, dict] = Field(default_factory=dict)
    batch_receipts: dict[str, dict] = Field(default_factory=dict)
    source_sequences: dict[str, int] = Field(default_factory=dict)
    scenario_steps: list[dict] = Field(default_factory=list)
    saved_scenarios: dict[str, dict] = Field(default_factory=dict)
    chat_sessions: dict[str, dict] = Field(default_factory=dict)
    # Confirmed AgentState per (npc, conversation); candidates never land
    # here before the reply commits.
    agent_states: dict[str, dict] = Field(default_factory=dict)
    command_receipts: dict[str, dict] = Field(default_factory=dict)
    action_results: dict[str, dict] = Field(default_factory=dict)
    transient_receipts: dict[str, dict] = Field(default_factory=dict)
    hook_instances: dict[str, dict] = Field(default_factory=dict)
    npc_conversations: dict[str, dict] = Field(default_factory=dict)
    npc_memories: dict[str, list[dict]] = Field(default_factory=dict)
    prologue: dict = Field(default_factory=dict)
    beach_presets: dict[str, dict] = Field(default_factory=dict)
    scenario_replay: dict = Field(default_factory=dict)
