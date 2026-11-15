from .schemas import HookDefinition, HookFragment


class HarvestTestProvider:
    @staticmethod
    def definition():
        return HookDefinition(hook_id="harvest-public", provider_id="harvest-test", version=1,
                              slot="public_background", priority=10, event_ref="harvest-1")

    @staticmethod
    def private_definition():
        return HookDefinition(hook_id="harvest-npc-a", provider_id="harvest-test", version=1,
                              slot="private_context", priority=5, npc_scope=["npc-a"], event_ref="harvest-1")

    def provide(self, definition, *, npc_id, **_):
        if definition.hook_id == "harvest-public":
            return HookFragment.from_definition(definition, "Public harvest background")
        return HookFragment.from_definition(definition, "npc-a-private", secret=True)
