from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Budget:
    total: int
    reserved_output: int
    used: int
    counting: str = "estimated"


@dataclass
class ContextSnapshot:
    identity: dict
    facts: list[str]
    visible_messages: list[str]
    memories: list[str]
    hooks: object
    candidate_capabilities: list[str]
    dependencies: dict
    budget: Budget
    trimmed: list[str] = field(default_factory=list)


class ContextAssembler:
    def __init__(self, *, total_budget: int, reserved_output: int = 800):
        if total_budget <= reserved_output:
            raise ValueError("budget_must_reserve_output")
        self.total_budget = total_budget
        self.reserved_output = reserved_output

    @staticmethod
    def _tokens(value):
        return max(1, (len(value) + 3) // 4)

    def build(self, *, identity, facts, visible_messages, memories, hooks, candidate_capabilities, source_versions):
        limit = self.total_budget - self.reserved_output
        sections = [("facts", list(facts)), ("visible_messages", list(visible_messages)),
                    ("memories", list(memories)), ("hooks", [x.content for x in hooks.applied])]
        trimmed = []
        used = 0
        kept = {}
        for name, values in sections:
            output = []
            for value in values:
                cost = self._tokens(value)
                if used + cost <= limit:
                    output.append(value); used += cost
                else:
                    trimmed.append(name)
            kept[name] = output
        dependencies = {"run_epoch": identity.get("run_epoch"), "npc_id": identity.get("npc_id"),
                        "hook_versions": dict(getattr(hooks, "dependencies", {})), **source_versions}
        return ContextSnapshot(identity=identity, facts=kept["facts"], visible_messages=kept["visible_messages"],
                               memories=kept["memories"], hooks=hooks, candidate_capabilities=candidate_capabilities,
                               dependencies=dependencies, budget=Budget(self.total_budget, self.reserved_output, used),
                               trimmed=trimmed)
