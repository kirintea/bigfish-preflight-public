from core.game.actions import ActionService


def test_social_response_is_constrained_and_idempotent(tmp_path):
    service = ActionService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    created = service.submit(world.world_id, "npc-a", "social_response", {"response": "accept"})
    assert created.status == "succeeded"
    duplicate = service.submit(world.world_id, "npc-a", "social_response", {"response": "accept"},
                               action_id=created.action_id)
    assert duplicate == created


def test_guide_requires_known_location(tmp_path):
    service = ActionService.for_test(tmp_path)
    world = service.create_world(["npc-a"])
    result = service.submit(world.world_id, "npc-a", "guide_to_location", {"location_id": "missing"})
    assert result.status == "rejected"
