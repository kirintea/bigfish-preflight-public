"""Load static NPC role profiles from configs/npcs/*.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import NpcProfile

_DEFAULT_DIR = Path("configs") / "npcs"
_cache: dict[str, NpcProfile] = {}


def load_npc_profile(
    npc_id: str, configs_dir: str | Path | None = None,
) -> NpcProfile:
    """Read and validate ``configs/npcs/{npc_id}.yaml`` (cached)."""
    directory = Path(configs_dir) if configs_dir is not None else _DEFAULT_DIR
    cache_key = f"{directory}:{npc_id}"
    if cache_key not in _cache:
        path = directory / f"{npc_id}.yaml"
        if not path.is_file():
            raise KeyError(f"npc profile not found: {npc_id}")
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        profile = NpcProfile.model_validate(data)
        if profile.npc_id != npc_id:
            raise ValueError("npc profile identity mismatch")
        _cache[cache_key] = profile
    return _cache[cache_key]


def load_system_prompt(
    npc_id: str, configs_dir: str | Path | None = None,
) -> str:
    """Session ``system_prompt_loader``: persona prompt for ``npc_id``.

    Falls back to a neutral identity line when the profile is missing so a
    single unknown NPC cannot break session creation.
    """
    try:
        return load_npc_profile(npc_id, configs_dir).system_prompt
    except (KeyError, ValueError, OSError):
        return f"你是 {npc_id}。"
