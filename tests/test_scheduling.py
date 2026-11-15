def test_scheduler_reuses_opportunity_and_enforces_one_active_generation():
    from core.conversation.scheduler import OpportunityScheduler

    scheduler = OpportunityScheduler(seed=42)
    first = scheduler.schedule("conv", "m1", ["npc-a", "npc-b"], direct_target="npc-b")
    assert scheduler.schedule("conv", "m1", ["npc-a", "npc-b"], direct_target="npc-b") == first
    scheduler.start(first.opportunity_id)
    assert scheduler.active("conv") == first.opportunity_id
    scheduler.finish(first.opportunity_id)
    assert scheduler.active("conv") is None
