"""US2: GET/POST /api/settings."""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from codesensei.config import get_settings


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("MASTER_KEY_FILE", raising=False)
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_store(monkeypatch):
    """In-memory replacement for the store + runtime layer."""
    rows: dict[str, str] = {}

    async def fake_get_effective():
        return {
            k: rows.get(k)
            for k in (
                "LLM_PROVIDER",
                "EMBEDDING_PROVIDER",
                "LLM_MODEL",
                "EMBEDDING_MODEL",
                "OLLAMA_BASE_URL",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "GITHUB_TOKEN",
            )
        }

    async def fake_set(key, value):
        rows[key] = value

    async def fake_delete(key):
        rows.pop(key, None)

    async def fake_apply():
        return None

    monkeypatch.setattr(
        "codesensei.settings_store.api.store.get_effective_settings", fake_get_effective
    )
    monkeypatch.setattr("codesensei.settings_store.api.store.set_setting", fake_set)
    monkeypatch.setattr("codesensei.settings_store.api.store.delete_setting", fake_delete)
    monkeypatch.setattr("codesensei.settings_store.api.apply_store_overrides_to_env", fake_apply)
    return rows


async def test_get_returns_redacted_state(async_client, fake_store):
    fake_store["OPENAI_API_KEY"] = "sk-test-abcd"
    resp = await async_client.get("/api/settings/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["credentials"]["openai_api_key"]["set"] is True
    assert body["credentials"]["openai_api_key"]["fingerprint"] == "…abcd"
    assert "sk-test-abcd" not in resp.text  # plaintext never on the wire
    assert body["master_key_present"] is True


async def test_get_empty_state(async_client, fake_store):
    resp = await async_client.get("/api/settings/")
    body = resp.json()
    assert body["credentials"]["openai_api_key"]["set"] is False
    assert body["credentials"]["openai_api_key"]["fingerprint"] is None


async def test_post_unknown_field_rejected(async_client, fake_store):
    resp = await async_client.post("/api/settings/", json={"banana": 1})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_invalid_llm_provider_rejected(async_client, fake_store):
    resp = await async_client.post("/api/settings/", json={"active_llm_provider": "magic"})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_anthropic_embedding_rejected_with_002_message(async_client, fake_store):
    resp = await async_client.post(
        "/api/settings/", json={"active_embedding_provider": "anthropic"}
    )
    assert resp.status_code == 400
    msg = resp.json()["error"]["message"]
    assert "EMBEDDING_PROVIDER=anthropic is not supported" in msg
    assert "openai, ollama" in msg


async def test_post_secret_without_master_key_locked(async_client, fake_store, monkeypatch):
    monkeypatch.delenv("MASTER_KEY", raising=False)
    get_settings.cache_clear()
    resp = await async_client.post("/api/settings/", json={"openai_api_key": "sk-anything"})
    assert resp.status_code == 503
    assert resp.json()["error"]["category"] == "settings_locked"
    assert "MASTER_KEY" in resp.json()["error"]["message"]


async def test_post_happy_writes_and_returns_state(async_client, fake_store):
    resp = await async_client.post(
        "/api/settings/",
        json={"active_llm_provider": "anthropic", "anthropic_api_key": "sk-ant-wxyz"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_llm_provider"] == "anthropic"
    assert body["credentials"]["anthropic_api_key"]["set"] is True
    assert body["credentials"]["anthropic_api_key"]["fingerprint"] == "…wxyz"
    # written rows visible in our in-memory fake
    assert fake_store["LLM_PROVIDER"] == "anthropic"
    assert fake_store["ANTHROPIC_API_KEY"] == "sk-ant-wxyz"


async def test_post_empty_string_clears_field(async_client, fake_store):
    fake_store["OPENAI_API_KEY"] = "sk-existing-1234"
    resp = await async_client.post("/api/settings/", json={"openai_api_key": ""})
    assert resp.status_code == 200
    assert "OPENAI_API_KEY" not in fake_store


async def test_post_logs_no_secret_plaintext(async_client, fake_store, caplog):
    caplog.set_level(logging.INFO)
    canary = "sk-CANARY-SECRET-ZZZZ"
    resp = await async_client.post("/api/settings/", json={"openai_api_key": canary})
    assert resp.status_code == 200
    blob = " ".join(rec.getMessage() for rec in caplog.records) + " ".join(
        str(rec.args or "") for rec in caplog.records
    )
    assert canary not in blob
