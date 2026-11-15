from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    memory_id: str
    world_id: str
    owner_npc_id: str
    content: str
    source_event_ids: list[str]
    acquisition: str = "direct"
    certainty: str = "confirmed"
    occurred_at_tick: int | None = None
    observed_at_tick: int | None = None
    access_state: str = "detail"
    protected_by: list[str] = field(default_factory=list)
    importance: float = 0.5
    revision: int = 1
    valid: bool = True
    last_access_tick: int = 0
    compression_version: int | None = None

    def as_dict(self):
        return self.__dict__.copy()


@dataclass
class MemorySearchResult:
    items: list[MemoryEntry]
    excluded: dict[str, int] = field(default_factory=dict)


@dataclass
class CompressionCandidate:
    version: int
    facts: list[str]
    claims: list[str]
    interpretations: list[str]
    active_commitments: list[str]
    source_refs: list[str]
    source_memory_ids: list[str]
