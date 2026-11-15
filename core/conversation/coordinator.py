from .delivery import deliver
from .schemas import Conversation


class ConversationCoordinator:
    def create(self, world_id, run_epoch, members, *, mode="npc_autonomous", topic=None):
        return Conversation.create(world_id, run_epoch, members, mode=mode, topic=topic)

    def change_members(self, conversation, members):
        if conversation.status == "closed":
            raise ValueError("conversation_closed")
        candidate = Conversation.create(conversation.world_id, conversation.run_epoch, members,
                                        mode=conversation.mode, topic=conversation.topic)
        conversation.members = candidate.members
        conversation.member_revision += 1
        conversation.knowledge = {member: conversation.knowledge.get(member, []) for member in conversation.members}
        return conversation

    def submit_message(self, conversation, author_id, content, targets=None):
        if author_id not in conversation.members:
            raise ValueError("member_not_active")
        return deliver(conversation, author_id=author_id, content=content, target_ids=targets)

    def pause(self, conversation, reason):
        if conversation.mode == "npc_autonomous":
            return conversation
        conversation.pause_reasons.add(reason)
        conversation.status = "paused"
        return conversation

    def resume(self, conversation, reason):
        conversation.pause_reasons.discard(reason)
        if not conversation.pause_reasons and conversation.status != "closed":
            conversation.status = "open"
        return conversation
