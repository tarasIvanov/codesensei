"""US4 integration: /healthz envelope contains providers.llm + providers.embedding."""

from __future__ import annotations

import pytest

from codesensei.providers.base import ProviderState


@pytest.mark.asyncio
async def test_healthz_includes_providers_when_all_ok(async_client, mock_probes):
    mock_probes({"db": "ok", "vector": "ok"}, "ok")
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["providers"] == {"llm": "ok", "embedding": "ok"}
    assert body["status"] == "ok"
    assert "failing" not in body


@pytest.mark.asyncio
async def test_providers_unconfigured_does_not_flip_overall_status(async_client, mock_probes):
    mock_probes(
        {"db": "ok", "vector": "ok"},
        "ok",
        llm=ProviderState.UNCONFIGURED,
        embedding=ProviderState.UNREACHABLE,
    )
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providers"] == {"llm": "unconfigured", "embedding": "unreachable"}


@pytest.mark.asyncio
async def test_providers_do_not_appear_in_failing(async_client, mock_probes):
    mock_probes(
        {"db": "down", "vector": "ok"},
        "ok",
        llm=ProviderState.UNREACHABLE,
        embedding=ProviderState.UNREACHABLE,
    )
    response = await async_client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["failing"] == ["db"]
    assert body["providers"] == {"llm": "unreachable", "embedding": "unreachable"}


@pytest.mark.asyncio
async def test_api_healthz_alias_includes_providers(async_client, mock_probes):
    mock_probes({"db": "ok", "vector": "ok"}, "ok")
    response = await async_client.get("/api/healthz")
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
