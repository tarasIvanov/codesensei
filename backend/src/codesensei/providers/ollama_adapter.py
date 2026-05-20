"""Ollama adapter — chat + embeddings via local Ollama HTTP API."""

from __future__ import annotations

import httpx

from codesensei.config import get_settings
from codesensei.providers.base import ChatMessage, ChatUsage
from codesensei.providers.errors import ProviderError, classify_http_status

DEFAULT_CHAT_MODEL = "llama3.1:8b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return ProviderError("ollama", str(exc), retryable=classify_http_status(code))
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError("ollama", str(exc), retryable=True)
    if isinstance(exc, httpx.HTTPError):
        return ProviderError("ollama", str(exc), retryable=True)
    return ProviderError("ollama", str(exc), retryable=False)


class OllamaChatProvider:
    name = "ollama"

    def __init__(self) -> None:
        self._last_usage: ChatUsage | None = None

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        chosen = model or get_settings().llm_model or DEFAULT_CHAT_MODEL
        base = get_settings().ollama_base_url.rstrip("/")
        payload = {
            "model": chosen,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{base}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise _translate(exc) from exc

        prompt_eval = data.get("prompt_eval_count")
        eval_count = data.get("eval_count")
        if prompt_eval is not None and eval_count is not None:
            self._last_usage = ChatUsage(
                prompt_tokens=prompt_eval,
                completion_tokens=eval_count,
                model=chosen,
            )

        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise ProviderError("ollama", "empty completion", retryable=False)
        return content


class OllamaEmbeddingProvider:
    name = "ollama"

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts or any(not t for t in texts):
            raise ProviderError("ollama", "empty input", retryable=False)
        chosen = model or get_settings().embedding_model or DEFAULT_EMBED_MODEL
        base = get_settings().ollama_base_url.rstrip("/")

        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for text in texts:
                    response = await client.post(
                        f"{base}/api/embeddings",
                        json={"model": chosen, "prompt": text},
                    )
                    response.raise_for_status()
                    body = response.json()
                    vec = body.get("embedding")
                    if not vec:
                        raise ProviderError("ollama", "empty embedding", retryable=False)
                    vectors.append(vec)
        except ProviderError:
            raise
        except Exception as exc:
            raise _translate(exc) from exc

        return vectors
