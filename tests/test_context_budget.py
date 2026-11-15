from core.agent.context import ContextAssembler
from core.hooks.assembler import HookAssembly
from core.hooks.schemas import HookFragment


def test_context_budget_reserves_output_and_trims_optional_sections():
    hooks = HookAssembly(applied=[HookFragment(hook_id="public", provider_id="p", version=1, slot="topic", content="hook " * 30)])
    result = ContextAssembler(total_budget=20, reserved_output=5).build(
        identity={"world_id": "w", "run_epoch": "e", "npc_id": "n"}, facts=["fact " * 20],
        visible_messages=["message " * 20], memories=["memory " * 20], hooks=hooks,
        candidate_capabilities=["speak"], source_versions={},
    )
    assert result.budget.total == 20
    assert result.budget.reserved_output == 5
    assert result.budget.used <= 15
    assert result.trimmed
    assert result.budget.counting == "estimated"
