from dataclasses import dataclass


@dataclass
class SaveSnapshot:
    snapshot_id: str
    schema_version: int
    content_version: str
    checksum: str
    created_at: str
    source_revision: int
    world_id: str
    world: dict


@dataclass
class LoadedSnapshot:
    snapshot_id: str
    checksum: str
    world: dict
    source_revision: int
