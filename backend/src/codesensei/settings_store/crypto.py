"""Fernet wrapper keyed on Settings.master_key (env-only, never persisted)."""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from codesensei.config import get_settings


class SettingsCryptoError(Exception):
    """Raised on encrypt(...) when MASTER_KEY is missing or malformed."""


def _fernet() -> Fernet:
    key = get_settings().master_key
    if not key:
        raise SettingsCryptoError("MASTER_KEY is not configured.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SettingsCryptoError("MASTER_KEY is not a valid Fernet key.") from exc


def is_master_key_valid() -> bool:
    try:
        _fernet()
    except SettingsCryptoError:
        return False
    return True


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt or raise InvalidToken / SettingsCryptoError."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise
