"""Provider health probes — no paid API calls (research.md R7)."""

from __future__ import annotations

import httpx
import structlog

from codesensei.config import get_settings
from codesensei.providers.base import ProviderProbeResult, ProviderState
from codesensei.providers.errors import ProviderError
from codesensei.providers.factory import get_embedding_provider, get_llm_provider


async def _probe_openai_key_presence() -> ProviderState:
    if get_settings().openai_api_key:
        return ProviderState.OK
    return ProviderState.UNCONFIGURED


async def _probe_anthropic_key_presence() -> ProviderState:
    if get_settings().anthropic_api_key:
        return ProviderState.OK
    return ProviderState.UNCONFIGURED


async def _probe_ollama_reachability() -> ProviderState:
    base = get_settings().ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{base}/api/tags")
            return ProviderState.OK if response.status_code == 200 else ProviderState.UNREACHABLE
    except httpx.HTTPError:
        return ProviderState.UNREACHABLE


async def probe_llm_provider() -> ProviderProbeResult:
    logger = structlog.get_logger()
    try:
        provider = get_llm_provider()
    except ProviderError as exc:
        logger.warning("probe.llm.config_error", message=exc.message)
        return ProviderProbeResult(state=ProviderState.UNCONFIGURED, provider=None)

    name = provider.name
    if name == "openai":
        state = await _probe_openai_key_presence()
    elif name == "anthropic":
        state = await _probe_anthropic_key_presence()
    elif name == "ollama":
        state = await _probe_ollama_reachability()
    else:
        state = ProviderState.UNCONFIGURED

    if state is ProviderState.UNREACHABLE:
        logger.warning("probe.llm", provider=name, state=state.value)
    return ProviderProbeResult(state=state, provider=name)


async def probe_embedding_provider() -> ProviderProbeResult:
    logger = structlog.get_logger()
    try:
        provider = get_embedding_provider()
    except ProviderError as exc:
        logger.warning("probe.embedding.config_error", message=exc.message)
        return ProviderProbeResult(state=ProviderState.UNCONFIGURED, provider=None)

    name = provider.name
    if name == "openai":
        state = await _probe_openai_key_presence()
    elif name == "ollama":
        state = await _probe_ollama_reachability()
    else:
        state = ProviderState.UNCONFIGURED

    if state is ProviderState.UNREACHABLE:
        logger.warning("probe.embedding", provider=name, state=state.value)
    return ProviderProbeResult(state=state, provider=name)
