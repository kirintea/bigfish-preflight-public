from core.agent.context import ContextAssembler
from core.hooks.assembler import HookAssembly


def test_context_dependencies_include_epoch_npc_and_hook_versions():
    result = ContextAssembler(total_budget=100, reserved_output=20).build(
        identity={"world_id": "world-a", "run_epoch": "epoch-a", "npc_id": "npc-a"},
        facts=["fact"], visible_messages=["hello"], memories=[], hooks=HookAssembly(),
        candidate_capabilities=["speak"], source_versions={"knowledge": 2},
    )
    assert result.dependencies["run_epoch"] == "epoch-a"
    assert result.dependencies["npc_id"] == "npc-a"
    assert result.dependencies["hook_versions"] == {}
