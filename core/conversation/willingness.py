import hashlib
import random

from .schemas import Opportunity


def choose_opportunity(conversation_id, trigger, candidates, *, seed=0, rules=None):
    digest = hashlib.sha256(f"{conversation_id}:{trigger}:{seed}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    selected = rng.choice(candidates).npc_id if candidates else None
    return Opportunity(opportunity_id=hashlib.sha256(f"{conversation_id}:{trigger}".encode()).hexdigest()[:20],
                       trigger=trigger, conversation_id=conversation_id, selected_npc_id=selected,
                       candidates=list(candidates), rules=rules or {}, random_value=rng.random())
