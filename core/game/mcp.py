from __future__ import annotations

class NpcMcpFacade:
    """Thin, capability-limited facade; all writes delegate to ActionService."""

    def __init__(self, actions, context_reader):
        self.actions = actions
        self.context_reader = context_reader

    def observe_npc(self, world_id, npc_id):
        return self.context_reader(world_id, npc_id)

    def submit_npc_command(self, world_id, npc_id, capability, parameters=None, action_id=None):
        return self.actions.submit(world_id, npc_id, capability, parameters or {}, action_id=action_id)

    def get_npc_command(self, action_id):
        return self.actions.get(action_id)

    def cancel_npc_command(self, world_id, action_id):
        return self.actions.cancel(world_id, action_id)
