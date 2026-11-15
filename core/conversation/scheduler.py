from .eligibility import eligible_candidates
from .willingness import choose_opportunity


class OpportunityScheduler:
    def __init__(self, *, seed=0):
        self.seed = seed
        self._opportunities = {}
        self._active = {}

    def schedule(self, conversation_id, trigger, members, *, direct_target=None, busy=None, paused=None):
        key = conversation_id, trigger
        if key in self._opportunities:
            return self._opportunities[key]
        candidates = eligible_candidates(members=members, speaker=None, busy=busy or set(), paused=paused or set(),
                                          direct_targets=[direct_target] if direct_target else None)
        opportunity = choose_opportunity(conversation_id, trigger, candidates, seed=self.seed)
        self._opportunities[key] = opportunity
        return opportunity

    def start(self, opportunity_id):
        opportunity = next((item for item in self._opportunities.values() if item.opportunity_id == opportunity_id), None)
        if opportunity is None:
            raise KeyError("opportunity_not_found")
        current = self._active.get(opportunity.conversation_id)
        if current and current != opportunity_id:
            raise ValueError("conversation_busy")
        self._active[opportunity.conversation_id] = opportunity_id

    def finish(self, opportunity_id):
        for conversation_id, active in list(self._active.items()):
            if active == opportunity_id:
                self._active.pop(conversation_id)

    def active(self, conversation_id):
        return self._active.get(conversation_id)
