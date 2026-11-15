from __future__ import annotations

from copy import deepcopy
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from core.game.repository import WorldRepository
from core.game.capabilities import ALLOWED_TRANSITIONS, validate_capability


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    npc_id: str
    capability: str
    status: str
    parameters: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    error_code: str | None = None


class ActionService:
    def __init__(self, repository):
        self.repository = repository
        self._results = {}

    @classmethod
    def for_test(cls, root):
        return cls(WorldRepository(root / "worlds"))

    def create_world(self, npc_ids):
        return self.repository.create("test", "world-" + uuid4().hex, uuid4().hex, npc_ids)

    def submit(self, world_id, npc_id, capability, parameters, *, action_id=None):
        action_id = action_id or uuid4().hex
        if action_id in self._results:
            return self._results[action_id]
        world = self.repository.read("test", world_id)
        validation_error = validate_capability(capability, parameters)
        if npc_id not in world.npc_ids:
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="rejected", parameters=parameters, error_code="unknown_npc")
        elif validation_error:
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="rejected", parameters=deepcopy(parameters), error_code=validation_error)
        elif capability == "social_response":
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="succeeded", parameters=deepcopy(parameters), result={"effect_applied": True})
        elif capability == "guide_to_location" and self._known_location(world, parameters.get("location_id")):
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="succeeded", parameters=deepcopy(parameters), result={"simulated": True})
        elif capability in {"move_to", "wander", "follow", "stop", "interact", "say", "reply"}:
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="accepted", parameters=deepcopy(parameters), result={"simulated": True})
        else:
            result = ActionResult(action_id=action_id, npc_id=npc_id, capability=capability,
                                  status="rejected", parameters=deepcopy(parameters), error_code="invalid_target" if capability == "guide_to_location" else "invalid_parameters")
        self._results[action_id] = result
        def mutate(candidate):
            candidate.action_results[action_id] = result.model_dump(mode="json")
            candidate.revision += 1
            return None, True
        self.repository.transact("test", world_id, mutate)
        return result

    def get(self, action_id):
        return self._results.get(action_id)

    def cancel(self, world_id, action_id):
        result = self._results.get(action_id)
        if result is None:
            world = self.repository.read("test", world_id)
            raw = world.action_results.get(action_id)
            if raw:
                result = ActionResult.model_validate(raw)
        if result is None:
            return None
        if result.status in {"succeeded", "failed", "cancelled", "expired", "rejected"}:
            return result
        result = result.model_copy(update={"status": "cancelled", "error_code": "cancelled"})
        self._results[action_id] = result
        def mutate(candidate):
            candidate.action_results[action_id] = result.model_dump(mode="json")
            candidate.revision += 1
            return None, True
        self.repository.transact("test", world_id, mutate)
        return result

    def transition(self, world_id, action_id, status):
        result = self.get(action_id)
        if result is None:
            raise KeyError("not_found")
        if status not in ALLOWED_TRANSITIONS.get(result.status, set()):
            raise ValueError("invalid_action_transition")
        updated = result.model_copy(update={"status": status})
        self._results[action_id] = updated
        def mutate(candidate):
            candidate.action_results[action_id] = updated.model_dump(mode="json")
            candidate.revision += 1
            return None, True
        self.repository.transact("test", world_id, mutate)
        return updated

    @staticmethod
    def _known_location(world, location_id):
        locations = world.domain_states.get("environment", {}).get(world.world_id, {}).get("data", {}).get("locations", [])
        return any((item.get("location_id") if isinstance(item, dict) else item) == location_id for item in locations)
