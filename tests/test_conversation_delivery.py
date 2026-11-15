def test_delivery_recomputes_actual_recipients_and_updates_only_recipients_knowledge():
    from core.conversation.delivery import deliver
    from core.conversation.schemas import Conversation

    conversation = Conversation.create("w", "e", ["npc-a", "npc-b", "npc-c"], mode="npc_autonomous")
    message = deliver(conversation, author_id="npc-a", content="secret", target_ids=["npc-b"])
    assert message.actual_recipient_ids == ["npc-b"]
    assert conversation.knowledge["npc-b"] == [message.message_id]
    assert conversation.knowledge["npc-c"] == []


def test_formal_pause_does_not_pause_autonomous_conversation():
    from core.conversation.coordinator import ConversationCoordinator

    c = ConversationCoordinator()
    formal = c.create("w", "e", ["player", "npc-a"], mode="player_formal")
    auto = c.create("w", "e", ["npc-a", "npc-b"], mode="npc_autonomous")
    c.pause(formal, "player_offline")
    assert formal.status == "paused"
    assert auto.status == "open"
