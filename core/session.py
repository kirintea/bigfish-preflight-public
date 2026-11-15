"""NPC session cache backed by confirmed state in the world aggregate.

Cache key = (namespace, world, NPC, conversation, epoch). The persistent
key is (world, NPC, conversation) — the epoch is carried by the world and
handled by the recovery protocol. Instance TTL only reclaims cache
entries; confirmed AgentState lives in the world aggregate's
``agent_states`` and is only replaced through ``commit_candidate``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from agentscope.agent import Agent
from agentscope.state import AgentState

from core.agent.factory import AgentFactory
from core.config.schemas import LLMConfig, OfflineModelMode

_SEPARATOR = ":"


def persist_key(world_id: str, npc_id: str, conversation_id: str) -> str:
    """Durable key inside ``world.agent_states`` (no epoch component)."""
    for part in (world_id, npc_id, conversation_id):
        if _SEPARATOR in part or not part:
            raise ValueError("invalid identity part")
    return _SEPARATOR.join((world_id, npc_id, conversation_id))


def cache_key(
    namespace: str, world_id: str, npc_id: str, conversation_id: str,
    run_epoch: str,
) -> tuple[str, str, str, str, str, str]:
    """In-memory cache key; includes the epoch so stale generations never
    serve a recovered world."""
    return (namespace, world_id, npc_id, conversation_id, run_epoch)


@dataclass
class NpcSession:
    namespace: str
    world_id: str
    npc_id: str
    conversation_id: str
    run_epoch: str
    agent: Agent

    @property
    def state(self) -> AgentState:
        """The working (candidate) state; not confirmed until commit."""
        return self.agent.state


@dataclass
class _CacheEntry:
    session: NpcSession
    expires_at: float


class NpcSessionManager:
    """Creates and caches per-(world, NPC, conversation, epoch) agents."""

    def __init__(
        self,
        repository,
        *,
        llm: LLMConfig | None = None,
        offline_mode: bool = True,
        offline_model_mode: OfflineModelMode = "valid_reply",
        ttl_seconds: float = 900.0,
        time_fn: Callable[[], float] = monotonic,
        system_prompt_loader: Callable[[str], str] | None = None,
        otel_enabled: bool = False,
    ) -> None:
        self._repository = repository
        self._llm = llm or LLMConfig()
        self._offline_mode = offline_mode
        self._offline_model_mode = offline_model_mode
        self._ttl = ttl_seconds
        self._time = time_fn
        self._system_prompt_loader = system_prompt_loader
        self._otel_enabled = otel_enabled
        self._cache: dict[tuple, _CacheEntry] = {}

    # -- confirmed state -------------------------------------------------

    def _load_confirmed(
        self, namespace: str, world_id: str, npc_id: str, conversation_id: str,
    ) -> AgentState | None:
        world = self._repository.read(namespace, world_id)
        raw = world.agent_states.get(persist_key(world_id, npc_id, conversation_id))
        if raw is None:
            return None
        return AgentState.model_validate(raw)

    def commit_candidate(
        self, *, namespace: str, world_id: str, npc_id: str,
        conversation_id: str, candidate: AgentState,
    ) -> None:
        """Publish the candidate as confirmed state via the world writer.

        The only path that may replace ``agent_states`` content; called
        after a reply has been validated and accepted for commit.
        """
        key = persist_key(world_id, npc_id, conversation_id)
        payload = json.loads(candidate.model_dump_json())

        def mutate(world):
            if world.agent_states.get(key) == payload:
                return None, False
            world.agent_states[key] = payload
            world.revision += 1
            return None, True

        self._repository.transact(namespace, world_id, mutate)

    # -- cache ------------------------------------------------------------

    def evict_expired(self) -> int:
        """Drop expired cache entries; confirmed state is never touched."""
        now = self._time()
        stale = [k for k, e in self._cache.items() if e.expires_at <= now]
        for k in stale:
            del self._cache[k]
        return len(stale)

    async def get_or_create(
        self, *, namespace: str, world_id: str, npc_id: str,
        conversation_id: str, run_epoch: str,
    ) -> NpcSession:
        key = cache_key(namespace, world_id, npc_id, conversation_id, run_epoch)
        entry = self._cache.get(key)
        if entry is not None and entry.expires_at > self._time():
            return entry.session

        confirmed = self._load_confirmed(namespace, world_id, npc_id, conversation_id)
        if confirmed is not None:
            # Deep copy: the candidate must diverge without touching the
            # confirmed snapshot held by the world aggregate.
            state = AgentState.model_validate(confirmed.model_dump())
        else:
            state = AgentState(
                session_id=_SEPARATOR.join((world_id, npc_id, conversation_id)),
            )
        state.session_id = _SEPARATOR.join((world_id, npc_id, conversation_id))

        prompt = (
            self._system_prompt_loader(npc_id)
            if self._system_prompt_loader
            else f"你是 {npc_id}。"
        )
        agent = AgentFactory.create(
            npc_id=npc_id,
            system_prompt=prompt,
            llm=self._llm,
            offline_mode=self._offline_mode,
            offline_model_mode=self._offline_model_mode,
            state=state,
            otel_enabled=self._otel_enabled,
        )
        session = NpcSession(
            namespace=namespace,
            world_id=world_id,
            npc_id=npc_id,
            conversation_id=conversation_id,
            run_epoch=run_epoch,
            agent=agent,
        )
        self._cache[key] = _CacheEntry(
            session=session, expires_at=self._time() + self._ttl,
        )
        return session
