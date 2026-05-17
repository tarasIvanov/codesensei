"""US1 unit tests: orchestrator (mocked DB + mocked EmbeddingProvider)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.service import IndexingService


class _FakeSession:
    """Just enough AsyncSession surface to satisfy IndexingService internals."""

    def __init__(self, store: dict) -> None:
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, *args, **kwargs):  # noqa: ARG002
        return MagicMock()

    async def commit(self):
        self.store["commits"] = self.store.get("commits", 0) + 1


def _make_service_with_mocks(monkeypatch, store: dict | None = None):
    store = store or {}

    def sessionmaker_factory():
        return _FakeSession(store)

    return IndexingService(sessionmaker_factory), store


@pytest.mark.asyncio
async def test_fill_repo_payload_too_large(monkeypatch, tmp_path: Path):
    """When chunks > 5000, raise PAYLOAD_TOO_LARGE before any embedding."""
    svc, _ = _make_service_with_mocks(monkeypatch)

    async def fake_chunk_repo(root):  # noqa: ARG001
        # Produce 5001 stub ChunkSpecs.
        from codesensei.indexing.chunker import ChunkSpec

        return [
            ChunkSpec(
                file_path=f"f{i}.py",
                language="python",
                start_line=1,
                end_line=1,
                content="x = 1",
            )
            for i in range(5001)
        ]

    monkeypatch.setattr("codesensei.indexing.service.chunk_repo", fake_chunk_repo)
    fake_provider = MagicMock(name="EmbeddingProvider", embed=AsyncMock())
    fake_provider.name = "openai"
    monkeypatch.setattr(
        "codesensei.indexing.service.get_embedding_provider", lambda: fake_provider
    )

    with pytest.raises(IndexError) as exc:
        await svc._fill_repo(
            repo_id=uuid4(),
            root=tmp_path,
            source="/local",
            delete_on_failure=True,
        )
    assert exc.value.category == IndexErrorCategory.PAYLOAD_TOO_LARGE
    # Embedding provider must NOT have been called.
    fake_provider.embed.assert_not_called()


@pytest.mark.asyncio
async def test_fill_repo_empty_records_zero_chunks(monkeypatch, tmp_path: Path):
    """Repo with no source files → 0 chunks, indexed_at still set, no embed calls."""
    svc, _ = _make_service_with_mocks(monkeypatch)

    async def fake_chunk_repo(root):  # noqa: ARG001
        return []

    monkeypatch.setattr("codesensei.indexing.service.chunk_repo", fake_chunk_repo)
    fake_provider = MagicMock(name="EmbeddingProvider", embed=AsyncMock())
    fake_provider.name = "openai"
    monkeypatch.setattr(
        "codesensei.indexing.service.get_embedding_provider", lambda: fake_provider
    )

    # Replace replace_chunks with a stub that captures the call.
    captured = {}

    async def fake_replace_chunks(
        session, *, repo_id, new_chunks, embedding_provider, embedding_model, indexed_at,
    ):
        captured["repo_id"] = repo_id
        captured["count"] = len(new_chunks)
        captured["provider"] = embedding_provider
        captured["model"] = embedding_model
        captured["indexed_at"] = indexed_at
        return len(new_chunks)

    monkeypatch.setattr("codesensei.indexing.service.replace_chunks", fake_replace_chunks)

    rid = uuid4()
    result = await svc._fill_repo(
        repo_id=rid, root=tmp_path, source="/local", delete_on_failure=False
    )
    assert result["chunk_count"] == 0
    assert captured["count"] == 0
    assert captured["repo_id"] == rid
    assert captured["provider"] == "openai"
    fake_provider.embed.assert_not_called()


@pytest.mark.asyncio
async def test_fill_repo_embedding_dim_mismatch(monkeypatch, tmp_path: Path):
    """Provider returns a wrong-dim vector → fail fast with dimension_mismatch."""
    svc, _ = _make_service_with_mocks(monkeypatch)

    from codesensei.indexing.chunker import ChunkSpec

    async def fake_chunk_repo(root):  # noqa: ARG001
        return [ChunkSpec("a.py", "python", 1, 1, "x = 1")]

    monkeypatch.setattr("codesensei.indexing.service.chunk_repo", fake_chunk_repo)
    fake_provider = MagicMock(name="EmbeddingProvider")
    fake_provider.name = "openai"
    # Wrong dim — 768 instead of 1536.
    fake_provider.embed = AsyncMock(return_value=[[0.0] * 768])
    monkeypatch.setattr(
        "codesensei.indexing.service.get_embedding_provider", lambda: fake_provider
    )

    with pytest.raises(IndexError) as exc:
        await svc._fill_repo(
            repo_id=uuid4(), root=tmp_path, source="/local", delete_on_failure=False
        )
    assert exc.value.category == IndexErrorCategory.EMBEDDING_DIMENSION_MISMATCH


@pytest.mark.asyncio
async def test_fill_repo_happy_path_writes_chunks(monkeypatch, tmp_path: Path):
    svc, _ = _make_service_with_mocks(monkeypatch)
    from codesensei.indexing.chunker import ChunkSpec

    async def fake_chunk_repo(root):  # noqa: ARG001
        return [
            ChunkSpec("a.py", "python", 1, 3, "def foo(): return 1"),
            ChunkSpec("b.md", "markdown", 1, 2, "# Hi"),
        ]

    monkeypatch.setattr("codesensei.indexing.service.chunk_repo", fake_chunk_repo)
    fake_provider = MagicMock(name="EmbeddingProvider")
    fake_provider.name = "openai"
    fake_provider.embed = AsyncMock(return_value=[[0.0] * 1536, [0.0] * 1536])
    monkeypatch.setattr(
        "codesensei.indexing.service.get_embedding_provider", lambda: fake_provider
    )

    captured = {}

    async def fake_replace_chunks(
        session, *, repo_id, new_chunks, embedding_provider, embedding_model, indexed_at,
    ):
        captured["chunks"] = list(new_chunks)
        return len(new_chunks)

    monkeypatch.setattr("codesensei.indexing.service.replace_chunks", fake_replace_chunks)

    result = await svc._fill_repo(
        repo_id=uuid4(), root=tmp_path, source="/local", delete_on_failure=False
    )
    assert result["chunk_count"] == 2
    assert len(captured["chunks"]) == 2
    assert captured["chunks"][0].file_path == "a.py"
    assert captured["chunks"][0].token_count > 0  # tiktoken-counted
    fake_provider.embed.assert_called_once()
