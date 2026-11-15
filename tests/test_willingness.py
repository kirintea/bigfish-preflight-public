def test_willingness_is_deterministic_and_uneligible_npcs_are_excluded():
    from core.conversation.eligibility import eligible_candidates
    from core.conversation.willingness import choose_opportunity

    candidates = eligible_candidates(
        members=["npc-a", "npc-b", "npc-c"], speaker="npc-a", busy={"npc-c"}, paused=set(),
        direct_targets=["npc-b"],
    )
    assert [x.npc_id for x in candidates] == ["npc-b"]
    first = choose_opportunity("conv", "message-1", candidates, seed=42)
    second = choose_opportunity("conv", "message-1", candidates, seed=42)
    assert first.opportunity_id == second.opportunity_id
    assert first.selected_npc_id == second.selected_npc_id
