from __future__ import annotations

CAPABILITIES = {
    "social_response": {"version": 1, "allowed": {"accept", "decline", "thank", "comfort"}, "requires_confirmation": True},
    "guide_to_location": {"version": 1, "requires_location": True, "simulated": True},
    "move_to": {"version": 1, "simulated": True},
    "wander": {"version": 1, "simulated": True},
    "follow": {"version": 1, "simulated": True},
    "stop": {"version": 1, "simulated": True},
    "interact": {"version": 1, "simulated": True},
    "say": {"version": 1, "simulated": True},
    "reply": {"version": 1, "simulated": True},
}

ALLOWED_TRANSITIONS = {
    "rejected": set(),
    "accepted": {"queued", "running", "succeeded", "failed", "cancelled", "expired"},
    "queued": {"running", "cancelled", "expired"},
    "running": {"succeeded", "failed", "cancelled", "expired"},
    "succeeded": set(), "failed": set(), "cancelled": set(), "expired": set(),
}

def validate_capability(capability: str, parameters: dict) -> str | None:
    spec = CAPABILITIES.get(capability)
    if spec is None:
        return "unknown_capability"
    if capability == "social_response" and parameters.get("response") not in spec["allowed"]:
        return "invalid_parameters"
    if capability == "guide_to_location" and not parameters.get("location_id"):
        return "invalid_target"
    return None
