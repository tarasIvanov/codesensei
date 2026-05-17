"""Bridge between persisted app_settings and runtime os.environ + Settings cache.

The provider factory is sync (lru_cache around pydantic Settings). To make
stored settings effective without changing every call site, we:

1. At app startup (lifespan), snapshot the .env-derived os.environ values
   for every whitelisted key. This is the deploy-time baseline.
2. At startup and after each POST /api/settings, merge baseline + stored
   values back into os.environ and clear the Settings cache. A stored value
   wins; a cleared store entry falls back to the baseline; if the baseline
   was empty too, the env-var becomes "" (which pydantic interprets as
   unconfigured).
"""
from __future__ import annotations

import os

import structlog

from codesensei.config import get_settings
from codesensei.providers.factory import _reset_provider_cache
from codesensei.settings_store.store import WHITELIST, get_effective_settings

_logger = structlog.get_logger()

_baseline: dict[str, str] = {}
_snapshot_taken = False


def snapshot_env_baseline() -> None:
    """Snapshot the .env-derived values once, at startup."""
    global _snapshot_taken
    if _snapshot_taken:
        return
    for key in WHITELIST:
        _baseline[key] = os.environ.get(key, "")
    _snapshot_taken = True


async def apply_store_overrides_to_env() -> None:
    """Read app_settings; merge baseline + stored into os.environ; clear caches."""
    snapshot_env_baseline()
    effective = await get_effective_settings()
    for key in WHITELIST:
        stored = effective.get(key)
        if stored is not None:
            os.environ[key] = stored
        else:
            os.environ[key] = _baseline.get(key, "")
    get_settings.cache_clear()
    _reset_provider_cache()
    _logger.info(
        "settings_store.applied",
        keys_set=sorted(k for k, v in effective.items() if v is not None),
    )
