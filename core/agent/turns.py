from __future__ import annotations

import asyncio
import json
import re
import traceback
from contextlib import nullcontext, suppress
from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from opentelemetry import trace
from agentscope.middleware import TracingMiddleware

from agentscope.message import Msg, TextBlock
from agentscope.model._utils import _StreamAccumulator
from core.agent.offline_model import OfflineChatModel
from core.config.schemas import LLMConfig, OfflineModelMode
from core.game.repository import WorldRepository
from core.game.schemas import WorldState
from core.session import NpcSessionManager
from core.hooks.assembler import HookAssembler


class ModelTurnError(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    conversation_id: str
    turn_id: str
    speaker_id: str
    trigger: Literal["player_message", "system", "scheduler"]
    text: str = Field(min_length=1, max_length=2000)
    allow_fallback: bool = True
    visible_context: str | None = None
    delivery_targets: list[str] = Field(default_factory=list)
    conversation_mode: str | None = None


class TurnResult(BaseModel):
    request_id: str
    conversation_id: str
    turn_id: str
    status: Literal["pending", "succeeded", "rejected", "fallback", "cancelled"]
    utterance: str = ""
    recipient_ids: list[str] = Field(default_factory=list)
    reply_to_message_id: str | None = None
    expression_id: str = "neutral"
    intent: dict | None = None
    basis_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None


class TurnService:
    def __init__(self, repository, sessions, *, offline_model_mode="valid_reply", logger=None, tracing=None, hook_registry=None):
        self.repository = repository
        self.sessions = sessions
        self.offline_model_mode = offline_model_mode
        self.logger = logger
        self.tracing = tracing
        self.hook_registry = hook_registry
        self._requests: dict[str, TurnResult] = {}
        self._active: dict[tuple[str, str], str] = {}

    @classmethod
    def for_test(cls, root, *, offline_model_mode="valid_reply", hook_registry=None):
        repo = WorldRepository(root / "worlds")
        sessions = NpcSessionManager(repo, offline_mode=True, offline_model_mode=offline_model_mode)
        return cls(repo, sessions, offline_model_mode=offline_model_mode, hook_registry=hook_registry)

    def create_world(self, npc_ids):
        return self.repository.create("test", "world-" + uuid4().hex, uuid4().hex, npc_ids)

    def reserve(self, world_id, conversation_id, turn_id):
        key = (world_id, conversation_id)
        if key in self._active:
            raise ValueError("conversation_busy")
        self._active[key] = turn_id

    def submit(self, world_id: str, request: TurnRequest, npc_id: str = "npc-a") -> TurnResult:
        return asyncio.run(self.submit_async(world_id, request, npc_id=npc_id))

    async def submit_async(
        self,
        world_id: str,
        request: TurnRequest,
        npc_id: str = "npc-a",
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> TurnResult:
        if request.request_id in self._requests:
            return self._requests[request.request_id]
        self.reserve(world_id, request.conversation_id, request.turn_id)
        try:
            with self.tracing.agent_scope() if self.tracing else nullcontext():
                result = await self._generate_async(world_id, npc_id, request, on_delta=on_delta)
            self._requests[request.request_id] = result
            return result
        finally:
            self._active.pop((world_id, request.conversation_id), None)

    async def _generate_async(self, world_id, npc_id, request, *, on_delta=None):
        world = self.repository.read("test", world_id)
        session = await self.sessions.get_or_create(namespace="test", world_id=world_id,
            npc_id=npc_id, conversation_id=request.conversation_id, run_epoch=world.run_epoch)
        tracing_middleware = next((middleware for middleware in session.agent._reply_middlewares
                                   if isinstance(middleware, TracingMiddleware)), None)
        if tracing_middleware is None or self.tracing is None:
            return await self._generate_candidate(world, session, request, on_delta=on_delta)

        result = None

        async def generate(**kwargs):
            nonlocal result
            trace.get_current_span().set_attributes({
                "bigfish.world.id": world_id, "bigfish.npc.id": npc_id,
                "bigfish.conversation.id": request.conversation_id,
                "bigfish.turn.id": request.turn_id, "bigfish.request.id": request.request_id,
            })
            result = await self._generate_candidate(world, session, request,
                on_delta=on_delta, tracing_middleware=tracing_middleware)
            if result.status == "fallback":
                raise ModelTurnError(result.error_code)
            yield Msg(name=npc_id, role="assistant", content=[TextBlock(text=result.utterance)])

        # The generation adapter retains validation/commit semantics while the
        # framework owns reply/model spans, payloads, usage, and stream lifetime.
        try:
            async for _ in tracing_middleware.on_reply(session.agent, {
                "inputs": Msg(name=request.speaker_id, role="user", content=[TextBlock(text=request.text)]),
            }, generate):
                pass
        except ModelTurnError:
            if result is None or result.status != "fallback":
                raise
        return result

    async def _generate_candidate(self, world, session, request, *, on_delta=None, tracing_middleware=None):
        world_id, npc_id = world.world_id, session.npc_id
        model = session.agent.model
        prior_context = list(session.state.context)
        input_msg = Msg(name='scheduler' if request.trigger == 'scheduler' else request.speaker_id,
                        role="user", content=[TextBlock(text=request.text)])
        session.state.context.append(input_msg)
        response = None
        api_response = None
        try:
            # Reuse the agent's own input assembly so the model receives the
            # system prompt (NPC persona), any compressed summary, and the
            # full candidate conversation — including this input and
            # previously committed NPC replies. Calling _call_api with the
            # bare context skips the system prompt and drops the role.
            prepared = await session.agent._prepare_model_input()
            if request.visible_context:
                # Refresh shared observations per turn; never accumulate snapshots in memory.
                prepared['messages'].insert(1, Msg(name='conversation', role='user',
                    content=[TextBlock(text=request.visible_context)]))
            if on_delta:
                prepared['messages'][0].content.append(TextBlock(
                    text='\n只输出你自己的角色台词，不输出 JSON、代码块或其他角色的台词。'))
            hook_text = self._hook_prompt(world, npc_id, request)
            if hook_text and prepared["messages"]:
                prepared["messages"][0].content.append(TextBlock(
                    text="\n\n当前世界规则与事件：\n" + hook_text,
                ))
            original_stream = model.stream
            try:
                if on_delta and not isinstance(model, OfflineChatModel):
                    model.stream = True
                async def call_model(**kwargs):
                    nonlocal api_response
                    api_response = await model._call_api(
                        model.model, kwargs["messages"], kwargs.get("tools"),
                    )
                    if tracing_middleware is not None and hasattr(api_response, "__aiter__"):
                        return self._traceable_stream(api_response)
                    return api_response

                if tracing_middleware is None:
                    call = call_model(**prepared)
                else:
                    call = tracing_middleware.on_model_call(session.agent, {
                        "current_model": model, **prepared,
                    }, call_model)
                response = await asyncio.wait_for(call, timeout=120)
            finally:
                model.stream = original_stream
            # OpenAI-compatible providers may prepend a ThinkingBlock. Only
            # a TextBlock is a user-visible candidate reply.
            chunks = []
            if hasattr(response, "__aiter__"):
                iterator = response.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(iterator), timeout=120)
                    except StopAsyncIteration:
                        break
                    if getattr(chunk, "is_last", False) and chunks:
                        continue
                    delta = "\n".join(
                        block.text for block in chunk.content
                        if getattr(block, "type", None) == "text" and getattr(block, "text", "")
                    )
                    if delta:
                        chunks.append(delta)
                        if on_delta and not ''.join(chunks).lstrip().startswith(('{', '[', '`')):
                            await on_delta(delta)
            else:
                chunks = [
                    "\n".join(block.text for block in response.content
                             if getattr(block, "type", None) == "text" and getattr(block, "text", ""))
                ]
            raw = "".join(chunks)
            if not raw:
                raise ValueError("missing_text_block")
            if getattr(model, "mode", None) == "invalid_json":
                raise ValueError("invalid_json")
            data = self._parse_output(raw)
            allowed = {"utterance", "recipient_ids", "reply_to_message_id", "expression_id", "intent", "basis_refs"}
            if set(data) - allowed or not isinstance(data.get("utterance"), str) or data.get("speaker"):
                raise ValueError("invalid_output")
            if request.delivery_targets:
                data["recipient_ids"] = list(request.delivery_targets)
            recipients = data.get("recipient_ids", [])
            if not recipients or any(x not in {"player", *world.npc_ids} for x in recipients):
                raise ValueError("invalid_recipient")
            intent = data.get("intent")
            if intent is not None and intent.get("candidate_id") not in {"social_response", "guide_to_location"}:
                raise ValueError("illegal_intent")
            result = TurnResult(request_id=request.request_id, conversation_id=request.conversation_id,
                turn_id=request.turn_id, status="succeeded", **{k: data.get(k) for k in allowed})
            if on_delta and (not hasattr(response, '__aiter__') or raw.lstrip().startswith(('{', '[', '`'))):
                await on_delta(result.utterance)
            latest = self.repository.read('test', world_id)
            if latest.run_epoch != world.run_epoch:
                raise ModelTurnError('stale_epoch')
            original_chat = world.chat_sessions.get(request.conversation_id)
            latest_chat = latest.chat_sessions.get(request.conversation_id)
            if original_chat and (not latest_chat or latest_chat['member_revision'] != original_chat['member_revision']):
                raise ModelTurnError('conversation_changed')
            session.state.context.append(Msg(name=npc_id, role="assistant", content=[TextBlock(text=raw)]))
            self.sessions.commit_candidate(namespace="test", world_id=world_id, npc_id=npc_id,
                conversation_id=request.conversation_id, candidate=session.state)
            return result
        except (asyncio.CancelledError, ModelTurnError):
            session.state.context[:] = prior_context
            raise
        except TimeoutError as exc:
            session.state.context[:] = prior_context
            self._log_failure("agent_model_timeout", request, world_id, npc_id, model, "model_timeout", exc)
            if not request.allow_fallback:
                raise ModelTurnError("model_timeout") from exc
            return self._fallback(request, "model_timeout", npc_id)
        except Exception as exc:
            session.state.context[:] = prior_context
            details = f"{type(exc).__name__}: {exc}"
            code = "model_unreachable" if re.search(r"connection|connect|apierror|event loop is closed|signal is aborted", details, re.I) else "invalid_model_output"
            event = "agent_model_error" if code == "model_unreachable" else "agent_output_rejected"
            self._log_failure(event, request, world_id, npc_id, model, code, exc)
            if not request.allow_fallback:
                raise ModelTurnError(code) from exc
            return self._fallback(request, code, npc_id)
        finally:
            for stream in (response, api_response if api_response is not response else None):
                if hasattr(stream, 'aclose'):
                    with suppress(Exception):
                        await stream.aclose()

    @staticmethod
    async def _traceable_stream(response):
        # AgentScope tracing reads the final chunk. Reuse its model accumulator
        # to retain the full reply and usage after trailing usage-only chunks.
        accumulator = _StreamAccumulator()
        has_final = False
        async for chunk in response:
            if chunk.is_last:
                has_final = True
            else:
                accumulator.append_chat_response(chunk)
                accumulator.id = chunk.id
            yield chunk
        if not has_final:
            yield accumulator.build()

    def _hook_prompt(self, world, npc_id, request):
        if self.hook_registry is None:
            return ""
        active = {
            hook_id for hook_id, item in world.hook_instances.items()
            if item.get("enabled") and npc_id in item.get("npc_ids", [])
        }
        if not active:
            return ""
        assembly = HookAssembler(self.hook_registry).assemble(
            world_id=world.world_id,
            npc_id=npc_id,
            tick=world.tick or 0,
            event_ids=list(world.events),
            conversation_mode=getattr(request, "conversation_mode", None),
            active_ids=active,
        )
        return assembly.prompt_text_for(npc_id)

    def _log_failure(self, event, request, world_id, npc_id, model, code, exc):
        if self.logger:
            self.logger.event(event, request.request_id, conversation_id=request.conversation_id,
                              turn_id=request.turn_id, world_id=world_id, npc_id=npc_id,
                              model=getattr(model, "model", "unknown"), error_code=code,
                              trace_id=f"{trace.get_current_span().get_span_context().trace_id:032x}",
                              exception_type=type(exc).__name__, exception_message=self._safe_error(exc),
                              traceback=self._safe_traceback())

    @staticmethod
    def _parse_output(raw):
        """Accept structured JSON when supplied, otherwise keep plain NPC text."""
        text = raw.strip()
        if text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        if text.startswith(("{", "[")):
            return json.loads(text)
        return {
            "utterance": text,
            "recipient_ids": ["player"],
            "reply_to_message_id": None,
            "expression_id": "neutral",
            "intent": None,
            "basis_refs": [],
        }

    @staticmethod
    def _safe_error(exc):
        return re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[=:]\s*[^\s,;]+", r"\1=[redacted]", str(exc))[:500]

    @staticmethod
    def _safe_traceback():
        return re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[=:]\s*[^\s,;]+", r"\1=[redacted]", traceback.format_exc())[-3000:]

    def _fallback(self, request, code, npc_id):
        return TurnResult(request_id=request.request_id, conversation_id=request.conversation_id,
            turn_id=request.turn_id, status="fallback", utterance=f"{npc_id} 暂时无法回应。",
            recipient_ids=request.delivery_targets or [request.speaker_id], error_code=code)

    def get(self, request_id):
        return self._requests.get(request_id)

    def cancel(self, request_id):
        result = self._requests.get(request_id)
        if result is None:
            return None
        if result.status == "pending":
            result = result.model_copy(update={"status": "cancelled", "error_code": "cancelled"})
            self._requests[request_id] = result
        return result
