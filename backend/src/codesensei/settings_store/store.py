"""Async CRUD for app_settings with Fernet wrap for secrets."""

from __future__ import annotations

from types import MappingProxyType

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from codesensei.db import get_sessionmaker
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.settings_store.crypto import SettingsCryptoError, decrypt, encrypt
from codesensei.settings_store.models import AppSetting

_logger = structlog.get_logger()

# Whitelist (per data-model.md R5).
WHITELIST: MappingProxyType[str, bool] = MappingProxyType(
    {
        "LLM_PROVIDER": False,
        "EMBEDDING_PROVIDER": False,
        "LLM_MODEL": False,
        "EMBEDDING_MODEL": False,
        "OLLAMA_BASE_URL": False,
        "OPENAI_API_KEY": True,
        "ANTHROPIC_API_KEY": True,
        "GITHUB_TOKEN": True,
    }
)


def is_known_key(key: str) -> bool:
    return key in WHITELIST


def is_secret_key(key: str) -> bool:
    return WHITELIST.get(key, False)


def _ensure_known(key: str) -> None:
    if not is_known_key(key):
        raise ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            f"Unknown settings key: {key}",
        )


async def get_setting(key: str) -> str | None:
    """Return plaintext for non-secret rows; decrypted plaintext for secrets; None if absent."""
    _ensure_known(key)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = (
            await session.execute(select(AppSetting).where(AppSetting.key == key))
        ).scalar_one_or_none()
    if row is None:
        return None
    if not row.is_secret:
        return row.value
    try:
        return decrypt(row.value)
    except (InvalidToken, SettingsCryptoError) as exc:
        _logger.warning("settings_store.decrypt_failed", key=key, error=str(exc))
        return None


async def get_setting_redacted(key: str) -> str | None:
    """Last-4 fingerprint for secrets; full value for non-secrets."""
    value = await get_setting(key)
    if value is None:
        return None
    if not is_secret_key(key):
        return value
    return "…" + value[-4:] if len(value) >= 4 else "…"


async def set_setting(key: str, value: str) -> None:
    """Insert/update. Empty value → delete (matches FR-015)."""
    _ensure_known(key)
    if value == "":
        await delete_setting(key)
        return
    is_secret = is_secret_key(key)
    stored = encrypt(value) if is_secret else value
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = insert(AppSetting).values(key=key, value=stored, is_secret=is_secret)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": stmt.excluded.value, "is_secret": is_secret},
        )
        await session.execute(stmt)
        await session.commit()


async def delete_setting(key: str) -> None:
    _ensure_known(key)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(delete(AppSetting).where(AppSetting.key == key))
        await session.commit()


async def get_effective_settings() -> dict[str, str | None]:
    """All whitelisted keys → plaintext (or None if not set)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = (await session.execute(select(AppSetting))).scalars().all()
    out: dict[str, str | None] = {k: None for k in WHITELIST}
    for row in rows:
        if row.key not in WHITELIST:
            continue
        if not row.is_secret:
            out[row.key] = row.value
        else:
            try:
                out[row.key] = decrypt(row.value)
            except (InvalidToken, SettingsCryptoError) as exc:
                _logger.warning("settings_store.decrypt_failed", key=row.key, error=str(exc))
                out[row.key] = None
    return out
