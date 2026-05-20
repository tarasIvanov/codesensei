"""Provider abstractions: protocols, types, probe-result shapes (data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypedDict, runtime_checkable


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]: ...


class ProviderState(StrEnum):
    OK = "ok"
    UNCONFIGURED = "unconfigured"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ProviderProbeResult:
    state: ProviderState
    provider: str | None = None


@dataclass(frozen=True)
class ChatUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str | None
