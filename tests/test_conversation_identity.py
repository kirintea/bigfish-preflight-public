import pytest


def test_autonomous_conversation_has_stable_identity_and_member_revision():
    from core.conversation.coordinator import ConversationCoordinator

    c = ConversationCoordinator()
    state = c.create("world-a", "epoch-a", ["npc-a", "npc-b", "npc-c"], topic="tide")
    assert state.mode == "npc_autonomous"
    assert state.world_id == "world-a" and state.run_epoch == "epoch-a"
    assert state.member_revision == 1
    updated = c.change_members(state, ["npc-a", "npc-c"])
    assert updated.member_revision == 2
    with pytest.raises(ValueError, match="member_not_active"):
        c.submit_message(updated, "npc-b", "late")


def test_player_formal_conversation_allows_player_but_autonomous_does_not():
    from core.conversation.schemas import Conversation

    formal = Conversation.create("w", "e", ["player", "npc-a"], mode="player_formal")
    assert "player" in formal.members
    with pytest.raises(ValueError, match="player_not_allowed"):
        Conversation.create("w", "e", ["player", "npc-a"], mode="npc_autonomous")
