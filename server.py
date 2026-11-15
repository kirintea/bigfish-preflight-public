import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from api.health import router as health_router
from api.observe import router as observe_router
from api.reports import router as reports_router
from api.context import router as context_router
from api.worlds import router as worlds_router
from api.test_control import router as test_control_router
from api.play import router as play_router
from api.chat import router as chat_router
from api.actions import router as actions_router
from api.npc import router as npc_router
from api.mcp import router as mcp_router
from api.hooks import router as hooks_router
from api.conversations import router as conversations_router
from api.memory import router as memory_router
from api.saves import router as saves_router
from core.config.schemas import AppConfig
from core.game.repository import WorldRepository
from core.reporting.service import ReportingService, outcome
from core.testing.runs import TestRuns
from core.log.logger import ServiceLog
from core.tracing.context import current_request
from core.tracing.events import EventStore
from core.tracing.setup import TracingSetup
from core.agent.turns import TurnService
from core.agent.profiles import load_system_prompt
from core.game.actions import ActionService
from core.hooks.registry import HookRegistry
from core.hooks.providers import HarvestTestProvider
from core.saves.service import SaveService
from middleware.request_context import RequestContextMiddleware


def create_app(config: AppConfig, *, span_exporter=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.config = config
        app.state.log = ServiceLog(config.storage_dir / "logs")
        tracing = None
        try:
            app.state.events = EventStore(config)
            tracing = TracingSetup(config, app.state.events, exporter=span_exporter, agent_only=True)
            app.state.tracing = tracing
            app.state.worlds = WorldRepository(config.storage_dir / "worlds")
            app.state.saves = SaveService(config.storage_dir / "saves", app.state.worlds)
            app.state.hook_registry = HookRegistry()
            harvest_provider = HarvestTestProvider()
            app.state.hook_registry.register(HarvestTestProvider.definition(), provider=harvest_provider)
            app.state.hook_registry.register(HarvestTestProvider.private_definition(), provider=harvest_provider)
            app.state.reporting = ReportingService(app.state.worlds, app.state.events, tracing)
            app.state.test_runs = TestRuns(app.state.worlds)
            app.state.turns = TurnService(app.state.worlds, __import__('core.session', fromlist=['NpcSessionManager']).NpcSessionManager(
                app.state.worlds, llm=config.llm, offline_mode=config.offline_mode,
                offline_model_mode=config.offline_model_mode, otel_enabled=config.otel_enabled,
                system_prompt_loader=load_system_prompt),
                offline_model_mode=config.offline_model_mode, logger=app.state.log, tracing=tracing,
                hook_registry=app.state.hook_registry)
            app.state.actions = ActionService(app.state.worlds)
            app.state.background_tasks = set()
            app.state.play_sessions = {}
            yield
        finally:
            deadline = time.monotonic() + config.shutdown_timeout_seconds
            tasks = getattr(app.state, "background_tasks", set())
            for task in tasks:
                task.cancel()
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=max(0, deadline - time.monotonic()))
                if pending:
                    app.state.events.increment("background_shutdown_timeouts")
            if tracing:
                tracing.shutdown(max(0, deadline - time.monotonic()))
                app.state.events.save_shutdown_status()
            worlds = getattr(app.state, "worlds", None)
            if worlds:
                worlds.close()
            app.state.log.close()

    app = FastAPI(title="Bigfish Agent", version=config.service_version, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        context = current_request.get()
        if "/reports" in request.url.path:
            reason = {401: "unauthenticated", 403: "forbidden_source", 404: "not_found"}.get(exc.status_code, "invalid_payload")
            return JSONResponse(outcome(reason), status_code=exc.status_code, headers=exc.headers)
        if exc.detail == "forbidden_source":
            return JSONResponse(outcome("forbidden_source"), status_code=exc.status_code)
        detail = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(exc.status_code, "request_rejected")
        command_errors = {'stale_epoch', 'revision_conflict', 'id_collision', 'run_capacity',
            'out_of_range', 'blocked_interaction', 'unreachable', 'encounter_required', 'depleted',
            'already_opened', 'dialogue_required', 'stale_speech', 'speech_not_visible', 'empty_message',
            'invalid_spawn', 'invalid_objects', 'checkpoint_inventory_mismatch', 'invalid_members',
            'minimum_members', 'observer_read_only', 'conversation_paused_or_empty', 'invalid_target',
            'unknown_reply', 'conversation_capacity', 'preset_capacity', 'replay_complete', 'invalid_replay_step',
            'model_timeout', 'invalid_model_output', 'model_unreachable', 'model_transport_error'}
        command_errors.update({'event_not_found', 'hook_not_registered', 'hook_not_active', 'hook_wrong_world', 'invalid_npc_scope'})
        command_errors.update({'npc_interaction_disabled', 'conversation_busy', 'conversation_changed'})
        if isinstance(exc.detail, str) and exc.detail in command_errors:
            detail = exc.detail
        return JSONResponse({"detail": detail, "request_id": context.request_id, "trace_id": context.trace_id},
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        context = current_request.get()
        if "/reports" in request.url.path:
            request.app.state.events.append(context, "report_validate", "rejected", "invalid_payload")
            errors = [".".join(map(str, e["loc"])) for e in exc.errors()]
            return JSONResponse(outcome("invalid_payload", errors=errors), status_code=422)
        return JSONResponse({"detail": "invalid_request", "request_id": context.request_id,
                             "trace_id": context.trace_id}, status_code=422)

    app.include_router(health_router)
    app.include_router(observe_router)
    app.include_router(reports_router)
    app.include_router(context_router)
    app.include_router(worlds_router)
    if config.test_control_enabled and config.environment != "production":
        app.include_router(test_control_router)
        app.include_router(play_router)
        app.include_router(chat_router)
        app.include_router(actions_router)
        app.include_router(npc_router)
        app.include_router(mcp_router)
        app.include_router(hooks_router)
        app.include_router(conversations_router)
        app.include_router(memory_router)
        app.include_router(saves_router)
    return app
