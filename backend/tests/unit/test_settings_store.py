"""US2: settings_store CRUD with whitelist + secret encryption (db mocked)."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from codesensei.config import get_settings
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.settings_store import store


class _FakeSession:
    def __init__(self, rows: dict[str, tuple[str, bool]]):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        from sqlalchemy.dialects.postgresql import Insert
        from sqlalchemy.sql.dml import Delete
        from sqlalchemy.sql.selectable import Select

        if isinstance(stmt, Insert):
            comp = stmt.compile()
            params = dict(comp.params)
            key = params["key"]
            self._rows[key] = (params["value"], params["is_secret"])
            return _FakeResult([])
        if isinstance(stmt, Delete):
            comp = stmt.compile()
            params = dict(comp.params)
            # naive: drop any row whose key matches a bound param
            for v in params.values():
                self._rows.pop(v, None)
            return _FakeResult([])
        if isinstance(stmt, Select):
            comp = stmt.compile()
            params = dict(comp.params)
            if params:
                # single key lookup
                k = next(iter(params.values()))
                if k in self._rows:
                    val, is_secret = self._rows[k]
                    return _FakeResult([_FakeRow(k, val, is_secret)])
                return _FakeResult([])
            # full table scan
            rows = [_FakeRow(k, v, s) for k, (v, s) in self._rows.items()]
            return _FakeResult(rows)
        return _FakeResult([])

    async def commit(self):
        return None


class _FakeRow:
    def __init__(self, key, value, is_secret):
        self.key = key
        self.value = value
        self.is_secret = is_secret


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSessionmaker:
    def __init__(self):
        self.rows: dict[str, tuple[str, bool]] = {}

    def __call__(self):
        return _FakeSession(self.rows)


@pytest.fixture
def fake_db(monkeypatch):
    sm = _FakeSessionmaker()
    monkeypatch.setattr("codesensei.settings_store.store.get_sessionmaker", lambda: sm)
    return sm


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_set_and_get_nonsecret(fake_db):
    await store.set_setting("LLM_PROVIDER", "anthropic")
    assert await store.get_setting("LLM_PROVIDER") == "anthropic"
    assert fake_db.rows["LLM_PROVIDER"] == ("anthropic", False)


async def test_set_and_get_secret_round_trip(fake_db):
    await store.set_setting("OPENAI_API_KEY", "sk-xyz-abcd")
    stored_value, is_secret = fake_db.rows["OPENAI_API_KEY"]
    assert is_secret is True
    assert stored_value != "sk-xyz-abcd"  # encrypted at rest
    assert await store.get_setting("OPENAI_API_KEY") == "sk-xyz-abcd"


async def test_get_setting_redacted_for_secret(fake_db):
    await store.set_setting("OPENAI_API_KEY", "sk-xyz-abcd")
    red = await store.get_setting_redacted("OPENAI_API_KEY")
    assert red == "…abcd"


async def test_empty_value_deletes_row(fake_db):
    await store.set_setting("LLM_PROVIDER", "anthropic")
    await store.set_setting("LLM_PROVIDER", "")
    assert "LLM_PROVIDER" not in fake_db.rows
    assert await store.get_setting("LLM_PROVIDER") is None


async def test_get_setting_unknown_key_rejected():
    with pytest.raises(ReviewError) as exc:
        await store.get_setting("BANANA")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


async def test_set_setting_unknown_key_rejected():
    with pytest.raises(ReviewError) as exc:
        await store.set_setting("BANANA", "x")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


async def test_effective_settings_returns_all_whitelisted_keys(fake_db):
    await store.set_setting("LLM_PROVIDER", "anthropic")
    await store.set_setting("ANTHROPIC_API_KEY", "sk-ant-zzzz")
    out = await store.get_effective_settings()
    assert out["LLM_PROVIDER"] == "anthropic"
    assert out["ANTHROPIC_API_KEY"] == "sk-ant-zzzz"  # decrypted
    assert out["OPENAI_API_KEY"] is None
    assert set(out.keys()) >= set(store.WHITELIST.keys())
