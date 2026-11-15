import os
import re
import tempfile
from pathlib import Path
from threading import RLock

from .schemas import WorldState

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def safe_id(value):
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value) or value.upper() in reserved:
        raise ValueError("invalid identifier")
    return value


class ResetConflict(Exception):
    pass


class WorldRepository:
    """One process owns this storage root; callers only receive detached snapshots."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._guard = RLock()
        self._locks = {}
        self._cache = {}
        self._owner = (self.root / ".writer.lock").open("a+b")
        try:
            if os.name == "nt":
                self._owner.seek(0)
                if not self._owner.read(1):
                    self._owner.write(b"0")
                    self._owner.flush()
                self._owner.seek(0)
                msvcrt.locking(self._owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._owner.close()
            raise RuntimeError("storage already has a writer") from None

    def close(self):
        if not self._owner.closed:
            if os.name == "nt":
                self._owner.seek(0)
                msvcrt.locking(self._owner.fileno(), msvcrt.LK_UNLCK, 1)
            self._owner.close()

    def __del__(self):
        owner = getattr(self, "_owner", None)
        if owner is not None and not owner.closed:
            self.close()

    def _path(self, namespace, world_id):
        if namespace not in {"production", "test"}:
            raise ValueError("invalid namespace")
        path = self.root / namespace / (safe_id(world_id) + ".json")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("invalid storage path")
        return path

    def _lock(self, namespace, world_id):
        self._path(namespace, world_id)
        if self._owner.closed:
            raise RuntimeError("writer is closed")
        with self._guard:
            return self._locks.setdefault((namespace, world_id), RLock())

    def _load(self, namespace, world_id):
        key = namespace, world_id
        if key not in self._cache:
            path = self._path(*key)
            if not path.exists():
                raise KeyError("not_found")
            world = WorldState.model_validate_json(path.read_bytes())
            if world.world_id != world_id:
                raise ValueError("invalid stored identity")
            self._cache[key] = world
        return self._cache[key]

    def read(self, namespace, world_id):
        with self._lock(namespace, world_id):
            return self._load(namespace, world_id).model_copy(deep=True)

    def create(self, namespace, world_id, run_epoch, npc_ids, **metadata):
        with self._lock(namespace, world_id):
            if self._path(namespace, world_id).exists():
                raise ValueError("world already exists")
            safe_id(run_epoch)
            if not npc_ids or len(npc_ids) != len(set(npc_ids)):
                raise ValueError("invalid NPC roster")
            for npc in npc_ids:
                safe_id(npc)
            world = WorldState(world_id=world_id, run_epoch=run_epoch, npc_ids=npc_ids, **metadata)
            self._persist(namespace, world)
            self._cache[namespace, world_id] = world
            return world.model_copy(deep=True)

    def transact(self, namespace, world_id, mutate):
        with self._lock(namespace, world_id):
            current = self._load(namespace, world_id)
            candidate = current.model_copy(deep=True)
            result, changed = mutate(candidate)
            if changed:
                candidate = WorldState.model_validate(candidate.model_dump())
                if candidate.world_id != current.world_id or candidate.run_epoch != current.run_epoch or candidate.revision != current.revision + 1:
                    raise ValueError("invalid transaction")
                self._persist(namespace, candidate)
                self._cache[namespace, world_id] = candidate
            return result

    def _replace(self, temporary, destination):
        os.replace(temporary, destination)

    def reset(self, namespace, world_id, run_epoch, *, prologue=None, initialize=None,
              expected_epoch=None, expected_revision=None):
        """Epoch changes use the same world lock and durable replacement as writes."""
        with self._lock(namespace, world_id):
            old = self._load(namespace, world_id)
            if expected_epoch is not None and old.run_epoch != expected_epoch:
                raise ResetConflict('stale_epoch')
            if expected_revision is not None and old.revision != expected_revision:
                raise ResetConflict('revision_conflict')
            safe_id(run_epoch)
            world = WorldState(world_id=old.world_id, run_epoch=run_epoch,
                npc_ids=old.npc_ids, test_run_id=old.test_run_id, name=old.name,
                revision=old.revision + 1, saved_scenarios=old.saved_scenarios,
                prologue=prologue or {}, beach_presets=old.beach_presets)
            if initialize:
                initialize(world)
                world = WorldState.model_validate(world.model_dump())
            self._persist(namespace, world)
            self._cache[namespace, world_id] = world
            return world.model_copy(deep=True)

    def restore(self, namespace, world_id, payload, run_epoch, *, expected_epoch=None):
        """Atomically publish a validated snapshot under a new execution epoch."""
        with self._lock(namespace, world_id):
            current = self._load(namespace, world_id)
            if expected_epoch is not None and current.run_epoch != expected_epoch:
                raise ResetConflict("stale_epoch")
            candidate = WorldState.model_validate(payload)
            if candidate.world_id != world_id or candidate.npc_ids != current.npc_ids:
                raise ValueError("snapshot_world_mismatch")
            candidate.run_epoch = run_epoch
            candidate.revision = current.revision + 1
            candidate = WorldState.model_validate(candidate.model_dump())
            self._persist(namespace, candidate)
            self._cache[namespace, world_id] = candidate
            return candidate.model_copy(deep=True)

    def _persist(self, namespace, world):
        destination = self._path(namespace, world.world_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".world-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                stream.write(world.model_dump_json())
                stream.flush()
                os.fsync(stream.fileno())
            self._replace(temporary, destination)
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
