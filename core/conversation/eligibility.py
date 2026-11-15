from .schemas import Candidate


def eligible_candidates(*, members, speaker, busy, paused, direct_targets=None):
    direct_targets = set(direct_targets or [])
    result = []
    for npc_id in members:
        if npc_id == speaker:
            continue
        if npc_id in paused:
            result.append(Candidate(npc_id, False, "paused")); continue
        if npc_id in busy:
            result.append(Candidate(npc_id, False, "busy_other_conversation")); continue
        if direct_targets and npc_id not in direct_targets:
            result.append(Candidate(npc_id, False, "not_targeted")); continue
        result.append(Candidate(npc_id, True, "direct_question" if direct_targets else "eligible"))
    return [candidate for candidate in result if candidate.eligible]
