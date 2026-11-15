from dataclasses import dataclass

from . import schemas as s


@dataclass(frozen=True)
class Domain:
    schema: type[s.StrictModel]
    entity: str
    readable: str
    supported: bool = True
    schema_version: int = 1


DOMAINS = {
    "world": Domain(s.WorldPayload, "world", "public"),
    "body": Domain(s.BodyPayload, "npc", "self"),
    "needs": Domain(s.NeedsPayload, "npc", "self"),
    "social": Domain(s.SocialPayload, "npc", "self"),
    "activity": Domain(s.ActivityPayload, "npc", "self"),
    "environment": Domain(s.EnvironmentPayload, "world", "filtered"),
    "resources": Domain(s.ResourcesPayload, "world", "filtered"),
    "groups": Domain(s.GroupsPayload, "world", "filtered"),
    "production": Domain(s.ProductionPayload, "world", "filtered"),
    "events": Domain(s.EventsPayload, "world", "knowledge"),
    "conversation": Domain(s.ConversationPayload, "conversation", "received"),
    "hooks": Domain(s.HooksPayload, "world", "filtered", False),
    "action_result": Domain(s.ActionResultPayload, "action", "self", False),
}
