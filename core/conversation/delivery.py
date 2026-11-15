from .schemas import Conversation, ConversationMessage


def deliver(conversation: Conversation, *, author_id, content, target_ids=None, tick=0,
            reply_to_message_id=None, intent_ref=None):
    if conversation.status != "open":
        raise ValueError("conversation_paused")
    if author_id not in conversation.members:
        raise ValueError("author_not_member")
    target_ids = list(target_ids or [member for member in conversation.members if member != author_id])
    if not set(target_ids) <= set(conversation.members) or author_id in target_ids:
        raise ValueError("invalid_recipients")
    actual = [member for member in conversation.members if member in target_ids and member != author_id]
    conversation.message_sequence += 1
    message = ConversationMessage(message_id=__import__("uuid").uuid4().hex, author_id=author_id,
        recipient_ids=target_ids, actual_recipient_ids=actual, content=content,
        sequence=conversation.message_sequence, tick=tick, reply_to_message_id=reply_to_message_id,
        intent_ref=intent_ref)
    conversation.messages.append(message)
    for recipient in actual:
        conversation.knowledge.setdefault(recipient, []).append(message.message_id)
    return message
