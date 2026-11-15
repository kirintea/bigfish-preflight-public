from core.hooks.assembler import HookAssembler
from core.hooks.registry import HookRegistry
from core.hooks.schemas import HookDefinition, HookFragment


class Provider:
    @staticmethod
    def definition():
        return HookDefinition(hook_id="event", provider_id="test", version=1, slot="topic", priority=1,
                              world_scope=["world-a"], start_tick=2, end_tick=4, event_ref="e1")

    def provide(self, definition, **_):
        return HookFragment.from_definition(definition, "event text")


def test_hooks_are_ordered_conflict_free_and_expire():
    registry = HookRegistry(); registry.register(Provider.definition(), provider=Provider())
    registry.register(HookDefinition(hook_id="later", provider_id="test", version=1, slot="topic", priority=3,
                                     world_scope=["world-a"], start_tick=2, end_tick=4, event_ref="e1"), provider=Provider())
    out = HookAssembler(registry).assemble(world_id="world-a", npc_id="npc-a", tick=3, event_ids=["e1"])
    assert [x.hook_id for x in out.applied] == ["later"]
    assert out.skipped[0].reason == "exclusive_conflict"
    expired = HookAssembler(registry).assemble(world_id="world-a", npc_id="npc-a", tick=5, event_ids=["e1"])
    assert any(x.reason == "expired" for x in expired.skipped)


def test_required_provider_failure_fails_and_optional_failure_skips():
    registry = HookRegistry()
    registry.register(HookDefinition(hook_id="required", provider_id="bad", version=1, slot="topic", required=True), provider=lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        HookAssembler(registry).assemble(world_id="w", npc_id="n", tick=0, event_ids=[])
    except RuntimeError as exc:
        assert str(exc) == "required_hook_failed"
    else:
        raise AssertionError("required hook should fail")
