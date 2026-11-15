from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .schemas import LoadedSnapshot, SaveSnapshot


class SaveService:
    schema_version = 1
    content_version = "world-state-v1"

    def __init__(self, root, repository):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.repository = repository

    def _path(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not snapshot_id.isalnum():
            raise ValueError("invalid_snapshot_id")
        path = self.root / f"{snapshot_id}.json"
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("invalid_snapshot_id")
        return path

    @staticmethod
    def _checksum(world):
        payload = json.dumps(world, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(payload).hexdigest()

    def _replace(self, temporary, destination):
        os.replace(temporary, destination)

    def create(self, namespace, world_id):
        world = self.repository.read(namespace, world_id)
        payload = world.model_dump(mode="json")
        snapshot_id = uuid4().hex
        record = {
            "snapshot_id": snapshot_id, "schema_version": self.schema_version,
            "content_version": self.content_version,
            "checksum": self._checksum(payload),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_revision": world.revision, "world_id": world.world_id, "world": payload,
        }
        destination = self._path(snapshot_id)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             prefix=".snapshot-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(record, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                stream.flush(); os.fsync(stream.fileno())
            self._replace(temporary, destination)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
        return SaveSnapshot(**record)

    def read(self, snapshot_id):
        path = self._path(snapshot_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("snapshot_invalid") from exc
        if record.get("schema_version") != self.schema_version or record.get("content_version") != self.content_version:
            raise ValueError("snapshot_incompatible")
        if record.get("checksum") != self._checksum(record.get("world", {})):
            raise ValueError("snapshot_checksum_mismatch")
        return LoadedSnapshot(snapshot_id=record["snapshot_id"], checksum=record["checksum"],
                              world=record["world"], source_revision=record["source_revision"])

    def restore(self, namespace, world_id, snapshot_id):
        snapshot = self.read(snapshot_id)
        if snapshot.world.get("world_id") != world_id:
            raise ValueError("snapshot_world_mismatch")
        return self.repository.restore(namespace, world_id, snapshot.world, uuid4().hex)
