from dataclasses import dataclass
from secrets import compare_digest
from typing import Literal

from fastapi import HTTPException, Request

from core.tracing.context import current_request


@dataclass(frozen=True)
class Principal:
    subject_id: str
    role: Literal["test_admin", "simulator"]
    world_ids: frozenset[str]
    source_ids: frozenset[str]


def require_source(principal, world_id, source_id):
    if principal.role != "simulator" or world_id not in principal.world_ids or source_id not in principal.source_ids:
        raise HTTPException(403, "forbidden")


def resolve_principal(request: Request):
    config = request.app.state.config
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(401, "unauthenticated", headers={"WWW-Authenticate": "Bearer"})
    for token, principal in (
        (config.test_admin_token, Principal("configured-admin", "test_admin", frozenset(), frozenset())),
        (config.simulator_token, Principal("configured-simulator", "simulator",
                                          config.simulator_world_ids, config.simulator_source_ids)),
    ):
        expected = token.get_secret_value()
        if expected and compare_digest(credential.encode(), expected.encode()):
            return principal
    raise HTTPException(401, "unauthenticated", headers={"WWW-Authenticate": "Bearer"})


def require_admin(request: Request):
    store, context = request.app.state.events, current_request.get()
    store.append(context, "auth", "started")
    try:
        principal = resolve_principal(request)
        if principal.role != "test_admin":
            raise HTTPException(403, "forbidden")
    except HTTPException as exc:
        store.append(context, "auth", "rejected", "unauthenticated" if exc.status_code == 401 else "forbidden")
        raise
    store.append(context, "auth", "ok")
    return principal
