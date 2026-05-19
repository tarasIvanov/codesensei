"""Auto-generate + persist MASTER_KEY via MASTER_KEY_FILE."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from codesensei.config import Settings, get_settings
from codesensei.settings_store import crypto
from codesensei.settings_store.master_key import resolve_from_file


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolve_from_file_generates_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "master.key"
    key = resolve_from_file(str(path))

    assert key, "non-empty key returned"
    assert path.exists()
    persisted = path.read_text(encoding="utf-8").strip()
    assert persisted == key
    Fernet(key.encode())


def test_resolve_from_file_returns_existing(tmp_path: Path) -> None:
    path = tmp_path / "master.key"
    pre = Fernet.generate_key().decode()
    path.write_text(pre, encoding="utf-8")

    key = resolve_from_file(str(path))
    assert key == pre


def test_resolve_is_stable_across_calls(tmp_path: Path) -> None:
    path = tmp_path / "master.key"
    a = resolve_from_file(str(path))
    b = resolve_from_file(str(path))
    assert a == b


def test_settings_validator_loads_keyfile(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "master.key"
    monkeypatch.delenv("MASTER_KEY", raising=False)
    monkeypatch.setenv("MASTER_KEY_FILE", str(path))

    s = Settings()
    assert s.master_key
    assert path.exists()
    Fernet(s.master_key.encode())


def test_env_master_key_takes_precedence_over_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "master.key"
    env_key = Fernet.generate_key().decode()
    monkeypatch.setenv("MASTER_KEY", env_key)
    monkeypatch.setenv("MASTER_KEY_FILE", str(path))

    s = Settings()
    assert s.master_key == env_key
    assert not path.exists()


def test_crypto_works_after_auto_gen(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "master.key"
    monkeypatch.delenv("MASTER_KEY", raising=False)
    monkeypatch.setenv("MASTER_KEY_FILE", str(path))
    get_settings.cache_clear()

    token = crypto.encrypt("hello")
    assert crypto.decrypt(token) == "hello"
