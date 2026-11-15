import pytest


def test_hook_scope_filters_private_content_and_wrong_world():
    from core.hooks.providers import HarvestTestProvider
    from core.hooks.registry import HookRegistry
    from core.hooks.assembler import HookAssembler

    registry = HookRegistry()
    provider = HarvestTestProvider()
    registry.register(HarvestTestProvider.definition(), provider=provider)
    registry.register(HarvestTestProvider.private_definition(), provider=provider)
    result = HookAssembler(registry).assemble(
        world_id="world-a", npc_id="npc-a", tick=3, event_ids=["harvest-1"],
        conversation_mode="formal",
    )
    assert [x.hook_id for x in result.applied] == ["harvest-public", "harvest-npc-a"]
    assert "npc-a-private" in result.applied[1].content
    assert "npc-a-private" not in result.public_text_for("npc-b")


def test_unregistered_and_secret_hooks_are_rejected():
    from core.hooks.schemas import HookDefinition, HookFragment
    from core.hooks.registry import HookRegistry
    from core.hooks.assembler import HookAssembler

    registry = HookRegistry()
    with pytest.raises(ValueError, match="provider_not_registered"):
        registry.register(HookDefinition(hook_id="x", provider_id="missing", version=1, slot="topic"))
    fragment = HookFragment(hook_id="x", provider_id="p", version=1, slot="topic", content="secret", secret=True)
    assert HookAssembler(registry).filter_fragment(fragment, world_id="world-a", npc_id="npc-a") is None
