from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator, model_validator

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Unit = Annotated[float, Field(ge=0, le=1)]
Quantity = Annotated[float, Field(ge=0)]
Tick = Annotated[int, Field(ge=0)]
Text = Annotated[str, StringConstraints(max_length=4096)]
PauseReason = Literal["manual", "dialogue", "offline", "idle"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, hide_input_in_errors=True)


class WorldPayload(StrictModel):
    tick: Tick | None = None
    speed: Annotated[float, Field(ge=0, le=100)] | None = None
    pause_reasons: list[PauseReason] | None = None
    scene: Text | None = None


class Condition(StrictModel):
    name: Text
    stage: Text | None = None
    severity: Unit | None = None


class BodyPayload(StrictModel):
    present: bool | None = None
    awake: bool | None = None
    downed: bool | None = None
    can_move: bool | None = None
    can_speak: bool | None = None
    conditions: list[Condition] | None = None


class Influence(StrictModel):
    name: Text
    value: Annotated[float, Field(ge=-1, le=1)]
    source: Text


class NeedsPayload(StrictModel):
    hunger: Unit | None = None
    fatigue: Unit | None = None
    rest: Unit | None = None
    mood: Unit | None = None
    influences: list[Influence] | None = None


class Opinion(StrictModel):
    target_id: Identifier
    value: Annotated[float, Field(ge=-1, le=1)] | None = None
    relationship: Literal["stranger", "friend", "family", "partner", "rival"] | None = None
    basis_event_ids: list[Identifier] | None = None


class SocialPayload(StrictModel):
    personality_ref: Identifier | None = None
    eligible: bool | None = None
    cooldown_until_tick: Tick | None = None
    opinions: list[Opinion] | None = None


class Schedule(StrictModel):
    start_tick: Tick
    end_tick: Tick
    activity: Text

    @model_validator(mode="after")
    def ordered(self):
        if self.end_tick < self.start_tick:
            raise ValueError("invalid schedule")
        return self


class ActivityPayload(StrictModel):
    task_id: Identifier | None = None
    phase: Literal["idle", "queued", "moving", "working", "completed", "failed", "cancelled"] | None = None
    target_id: Identifier | None = None
    target_kind: Literal["npc", "item", "location", "order"] | None = None
    progress: Unit | None = None
    schedule: list[Schedule] | None = None
    interruption_reason: Text | None = None


class Position(StrictModel):
    npc_id: Identifier
    location_id: Identifier | None = None
    x_m: float | None = None
    y_m: float | None = None
    distance_m: Quantity | None = None
    reachable: bool | None = None
    arrived: bool | None = None
    visible_to: list[Identifier] | None = None


class Location(StrictModel):
    location_id: Identifier
    blocked: bool | None = None
    visible_to: list[Identifier] | None = None


class EnvironmentPayload(StrictModel):
    weather: Literal["clear", "rain", "snow", "storm", "cloudy"] | None = None
    temperature_c: float | None = None
    positions: list[Position] | None = None
    locations: list[Location] | None = None


class Reservation(StrictModel):
    reservation_id: Identifier
    npc_id: Identifier
    quantity: Quantity


class Item(StrictModel):
    item_id: Identifier
    quantity: Quantity | None = None
    owner_id: Identifier | None = None
    holder_id: Identifier | None = None
    location_id: Identifier | None = None
    reservations: list[Reservation] | None = None
    visible_to: list[Identifier] | None = None

    @model_validator(mode="after")
    def sufficient(self):
        if self.quantity is not None and sum(r.quantity for r in self.reservations or []) > self.quantity:
            raise ValueError("over-reserved")
        return self


class ResourcesPayload(StrictModel):
    items: list[Item] | None = None


class Group(StrictModel):
    group_id: Identifier
    phase: Literal["forming", "active", "paused", "completed", "disbanded"] | None = None
    members: list[Identifier] | None = None
    roles: dict[Identifier, Text] | None = None
    visible_to: list[Identifier] | None = None


class GroupsPayload(StrictModel):
    groups: list[Group] | None = None


class Order(StrictModel):
    order_id: Identifier
    status: Literal["planned", "queued", "working", "blocked", "completed", "failed", "cancelled"] | None = None
    progress: Unit | None = None
    missing_materials: list[Identifier] | None = None
    visible_to: list[Identifier] | None = None


class Facility(StrictModel):
    facility_id: Identifier
    status: Literal["planned", "building", "ready", "damaged", "destroyed"] | None = None
    visible_to: list[Identifier] | None = None


class Crop(StrictModel):
    crop_id: Identifier
    growth: Unit | None = None
    status: Literal["sown", "growing", "ripe", "harvested", "dead"] | None = None
    visible_to: list[Identifier] | None = None


class ProductionPayload(StrictModel):
    orders: list[Order] | None = None
    facilities: list[Facility] | None = None
    crops: list[Crop] | None = None


class WorldEvent(StrictModel):
    event_id: Identifier
    fact: Text
    kind: Literal["confirmed", "hearsay"] = "confirmed"
    actor: Identifier | None = None
    targets: list[Identifier] = Field(default_factory=list)
    observers: list[Identifier] = Field(default_factory=list)
    actual_recipients: list[Identifier] = Field(default_factory=list)
    source: Literal["direct", "hearsay"] = "direct"
    source_event_id: Identifier | None = None
    location_id: Identifier | None = None
    occurred_at_tick: Tick | None = None
    observed_at_tick: Tick | None = None
    certainty: Unit | None = None

    @model_validator(mode="after")
    def separate_hearsay(self):
        if self.source == "hearsay" and self.kind != "hearsay":
            raise ValueError("hearsay requires claim semantics")
        return self


class EventsPayload(StrictModel):
    events: list[WorldEvent] | None = None


class Message(StrictModel):
    message_id: Identifier
    author: Identifier
    text: Text
    targets: list[Identifier] = Field(default_factory=list)
    actual_recipients: list[Identifier] = Field(default_factory=list)


class ConversationPayload(StrictModel):
    members: list[Identifier] | None = None
    status: Literal["open", "paused", "closed"] | None = None
    messages: list[Message] | None = None


class HooksPayload(StrictModel):
    hook_id: Identifier
    enabled: bool | None = None


class ActionResultPayload(StrictModel):
    status: Literal["accepted", "executing", "succeeded", "failed", "cancelled"]
    event_ids: list[Identifier] | None = None


class Envelope(StrictModel):
    schema_version: Literal[1]
    report_id: Identifier
    request_id: Identifier
    world_id: Identifier
    run_epoch: Identifier
    entity_id: Identifier
    source_kind: Literal["simulation", "test"]
    source_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    expected_revision: Tick
    mode: Literal["snapshot", "delta"]
    occurred_at_tick: Tick
    observed_at_tick: Tick

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("invalid schema version")
        return value

    @model_validator(mode="after")
    def chronology(self):
        if self.observed_at_tick < self.occurred_at_tick:
            raise ValueError("invalid time order")
        return self


class WorldReport(Envelope):
    domain: Literal["world"]
    payload: WorldPayload


class BodyReport(Envelope):
    domain: Literal["body"]
    payload: BodyPayload


class NeedsReport(Envelope):
    domain: Literal["needs"]
    payload: NeedsPayload


class SocialReport(Envelope):
    domain: Literal["social"]
    payload: SocialPayload


class ActivityReport(Envelope):
    domain: Literal["activity"]
    payload: ActivityPayload


class EnvironmentReport(Envelope):
    domain: Literal["environment"]
    payload: EnvironmentPayload


class ResourcesReport(Envelope):
    domain: Literal["resources"]
    payload: ResourcesPayload


class GroupsReport(Envelope):
    domain: Literal["groups"]
    payload: GroupsPayload


class ProductionReport(Envelope):
    domain: Literal["production"]
    payload: ProductionPayload


class EventsReport(Envelope):
    domain: Literal["events"]
    payload: EventsPayload


class ConversationReport(Envelope):
    domain: Literal["conversation"]
    payload: ConversationPayload


class HooksReport(Envelope):
    domain: Literal["hooks"]
    payload: HooksPayload


class ActionResultReport(Envelope):
    domain: Literal["action_result"]
    payload: ActionResultPayload


Report = Annotated[
    WorldReport | BodyReport | NeedsReport | SocialReport | ActivityReport | EnvironmentReport |
    ResourcesReport | GroupsReport | ProductionReport | EventsReport | ConversationReport |
    HooksReport | ActionResultReport, Field(discriminator="domain")]
REPORT_ADAPTER = TypeAdapter(Report)


class Batch(StrictModel):
    batch_id: Identifier
    expected_revision: Tick
    reports: Annotated[list[Report], Field(min_length=1, max_length=100)]


class ReportResult(StrictModel):
    status: Literal["accepted", "rejected", "duplicate", "conflict", "expired"]
    reason: str
    report_id: str | None
    request_id: str
    trace_id: str
    revision: int | None
    event_ids: list[str]
    errors: list[str] = Field(default_factory=list)
