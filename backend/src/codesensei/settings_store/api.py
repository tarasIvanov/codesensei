"""GET /api/settings + POST /api/settings — operator-facing CRUD."""

from __future__ import annotations

import time
from typing import Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from codesensei.config import get_settings
from codesensei.providers.factory import EMBEDDING_ACCEPTED, LLM_ACCEPTED
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.settings_store import store
from codesensei.settings_store.crypto import is_master_key_valid
from codesensei.settings_store.github_probe import probe_github
from codesensei.settings_store.runtime import apply_store_overrides_to_env

router = APIRouter(prefix="/settings", tags=["settings"])
_logger = structlog.get_logger()

# Map wire field names (lowercase JSON) → whitelisted DB keys (uppercase).
_FIELD_TO_KEY = {
    "active_llm_provider": "LLM_PROVIDER",
    "active_embedding_provider": "EMBEDDING_PROVIDER",
    "llm_model": "LLM_MODEL",
    "embedding_model": "EMBEDDING_MODEL",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "github_token": "GITHUB_TOKEN",
}
_SECRET_FIELDS = {"openai_api_key", "anthropic_api_key", "github_token"}


def _redact(value: str | None) -> dict[str, object]:
    if value is None or value == "":
        return {"set": False, "fingerprint": None}
    fp = "…" + value[-4:] if len(value) >= 4 else "…"
    return {"set": True, "fingerprint": fp}


async def _build_state() -> dict[str, object]:
    """State reflects the effective resolution: db row first, env fallback."""
    effective = await store.get_effective_settings()
    s = get_settings()

    def pick(key: str, env_value: str) -> str | None:
        v = effective.get(key)
        if v is not None and v != "":
            return v
        return env_value or None

    return {
        "active_llm_provider": pick("LLM_PROVIDER", s.llm_provider) or s.llm_provider,
        "active_embedding_provider": pick("EMBEDDING_PROVIDER", s.embedding_provider)
        or s.embedding_provider,
        "llm_model": pick("LLM_MODEL", s.llm_model) or "",
        "embedding_model": pick("EMBEDDING_MODEL", s.embedding_model) or "",
        "ollama_base_url": pick("OLLAMA_BASE_URL", s.ollama_base_url) or s.ollama_base_url,
        "credentials": {
            "openai_api_key": _redact(pick("OPENAI_API_KEY", s.openai_api_key)),
            "anthropic_api_key": _redact(pick("ANTHROPIC_API_KEY", s.anthropic_api_key)),
            "github_token": _redact(pick("GITHUB_TOKEN", s.github_token)),
        },
        "master_key_present": bool(s.master_key) and is_master_key_valid(),
    }


@router.get("/")
async def get_settings_endpoint() -> dict[str, object]:
    _logger.info("settings.read")
    return await _build_state()


@router.post("/")
async def post_settings(request: Request) -> dict[str, object]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ReviewError(ReviewErrorCategory.INVALID_INPUT, "Body must be a JSON object.")

    # Validate unknown fields first (no partial writes).
    unknown = [k for k in payload if k not in _FIELD_TO_KEY]
    if unknown:
        raise ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            f"Unknown settings field(s): {', '.join(unknown)}",
        )

    # Validate provider values + master-key presence before any write.
    llm_value = payload.get("active_llm_provider")
    if llm_value is not None and llm_value not in LLM_ACCEPTED:
        raise ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            f"LLM_PROVIDER={llm_value!r} is not supported; accepted values: "
            f"{', '.join(LLM_ACCEPTED)}",
        )
    embedding_value = payload.get("active_embedding_provider")
    if embedding_value is not None:
        if embedding_value == "anthropic":
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                "EMBEDDING_PROVIDER=anthropic is not supported because Anthropic "
                "has no embeddings API; accepted values: "
                f"{', '.join(EMBEDDING_ACCEPTED)}",
            )
        if embedding_value not in EMBEDDING_ACCEPTED:
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                f"EMBEDDING_PROVIDER={embedding_value!r} is not supported; accepted values: "
                f"{', '.join(EMBEDDING_ACCEPTED)}",
            )
    # Refuse secret writes if MASTER_KEY missing/invalid.
    needs_master = any(field in _SECRET_FIELDS and payload.get(field) for field in payload)
    if needs_master and not is_master_key_valid():
        raise ReviewError(
            ReviewErrorCategory.SETTINGS_LOCKED,
            "Settings storage is locked — set MASTER_KEY before saving credentials.",
        )

    # Apply writes.
    keys_set: list[str] = []
    keys_cleared: list[str] = []
    for field, value in payload.items():
        db_key = _FIELD_TO_KEY[field]
        if value is None or value == "":
            await store.delete_setting(db_key)
            keys_cleared.append(field)
        else:
            await store.set_setting(db_key, str(value))
            keys_set.append(field)

    await apply_store_overrides_to_env()
    _logger.info("settings.updated", keys_set=keys_set, keys_cleared=keys_cleared)
    return await _build_state()


class SettingsTestGithubResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: Literal[True]
    login: str
    scopes_hint: str | None = None
    elapsed_ms: int


@router.get("/test/github", response_model=SettingsTestGithubResponse)
async def test_github_endpoint() -> SettingsTestGithubResponse:
    """Read-only probe of the stored GitHub PAT — never echoes the PAT."""
    started = time.monotonic()
    login: str | None = None
    category: str | None = None
    status_code: int | None = None
    ok_flag = False
    try:
        token = await store.get_setting("GITHUB_TOKEN")
        if token is None or token == "":
            raise ReviewError(
                ReviewErrorCategory.SETTINGS_LOCKED,
                "GitHub PAT is not configured. Open Settings to add one.",
            )
        result = await probe_github(token)
        login = result["login"]
        scopes_hint = result["scopes_hint"]
        ok_flag = True
        status_code = 200
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return SettingsTestGithubResponse(
            ok=True,
            login=login or "",
            scopes_hint=scopes_hint,
            elapsed_ms=elapsed_ms,
        )
    except ReviewError as exc:
        category = exc.category.value
        status_code = exc.http_status
        raise
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _logger.info(
            "github_probe",
            ok=ok_flag,
            login=login,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            category=category,
        )
