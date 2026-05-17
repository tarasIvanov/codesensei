"""US2: Fernet round-trip + MASTER_KEY guard."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from codesensei.config import get_settings
from codesensei.settings_store import crypto


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _good_key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip(monkeypatch):
    monkeypatch.setenv("MASTER_KEY", _good_key())
    get_settings.cache_clear()
    out = crypto.encrypt("sk-secret-123")
    assert out != "sk-secret-123"
    assert crypto.decrypt(out) == "sk-secret-123"


def test_missing_key_blocks_encrypt(monkeypatch):
    monkeypatch.delenv("MASTER_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(crypto.SettingsCryptoError):
        crypto.encrypt("anything")
    assert crypto.is_master_key_valid() is False


def test_invalid_key_shape_blocks_encrypt(monkeypatch):
    monkeypatch.setenv("MASTER_KEY", "not-a-real-fernet-key")
    get_settings.cache_clear()
    with pytest.raises(crypto.SettingsCryptoError):
        crypto.encrypt("anything")
    assert crypto.is_master_key_valid() is False


def test_decrypt_with_wrong_key_raises(monkeypatch):
    monkeypatch.setenv("MASTER_KEY", _good_key())
    get_settings.cache_clear()
    token = crypto.encrypt("hello")
    monkeypatch.setenv("MASTER_KEY", _good_key())  # rotated to a different key
    get_settings.cache_clear()
    with pytest.raises(InvalidToken):
        crypto.decrypt(token)


def test_is_master_key_valid_true_for_good_key(monkeypatch):
    monkeypatch.setenv("MASTER_KEY", _good_key())
    get_settings.cache_clear()
    assert crypto.is_master_key_valid() is True
