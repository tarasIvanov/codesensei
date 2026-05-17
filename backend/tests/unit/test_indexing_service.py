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
    monkeypatch.setattr("codesensei.indexing.service.get_embedding_provider", lambda: fake_provider)

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
    monkeypatch.setattr("codesensei.indexing.service.get_embedding_provider", lambda: fake_provider)

    # Replace replace_chunks with a stub that captures the call.
    captured = {}

    async def fake_replace_chunks(
        session,
        *,
        repo_id,
        new_chunks,
        embedding_provider,
        embedding_model,
        indexed_at,
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
    monkeypatch.setattr("codesensei.indexing.service.get_embedding_provider", lambda: fake_provider)

    with pytest.raises(IndexError) as exc:
        await svc._fill_repo(
            repo_id=uuid4(), root=tmp_path, source="/local", delete_on_failure=False
        )
    assert exc.value.category == IndexErrorCategory.EMBEDDING_DIMENSION_MISMATCH


def test_enforce_chunk_token_cap_splits_oversize_chunk(monkeypatch):
    """Chunks above MAX_CHUNK_TOKENS must be split into sub-windows under the cap."""
    from codesensei.indexing.chunker import ChunkSpec
    from codesensei.indexing.service import MAX_CHUNK_TOKENS, IndexingService

    svc = IndexingService(sessionmaker=lambda: None)
    # Build a chunk well over the cap: ~3000 lines of "x = 1" → roughly 9000 tokens.
    lines = ["x = 1"] * 3000
    big = ChunkSpec(
        file_path="big.py",
        language="python",
        start_line=1,
        end_line=3000,
        content="\n".join(lines),
    )
    out_chunks, out_counts = svc._enforce_chunk_token_cap([big])
    assert len(out_chunks) >= 2  # split happened
    # No piece exceeds the cap.
    assert all(c <= MAX_CHUNK_TOKENS for c in out_counts)
    # Line numbers stay anchored to the original file (1-indexed, monotonic, contiguous).
    for sc in out_chunks:
        assert sc.start_line >= 1
        assert sc.end_line >= sc.start_line
    sorted_chunks = sorted(out_chunks, key=lambda c: c.start_line)
    for a, b in zip(sorted_chunks, sorted_chunks[1:], strict=False):
        assert b.start_line == a.end_line + 1


def test_enforce_chunk_token_cap_passes_small_chunk_through(monkeypatch):
    from codesensei.indexing.chunker import ChunkSpec
    from codesensei.indexing.service import IndexingService

    svc = IndexingService(sessionmaker=lambda: None)
    small = ChunkSpec("a.py", "python", 1, 5, "def foo():\n    return 1")
    out_chunks, out_counts = svc._enforce_chunk_token_cap([small])
    assert len(out_chunks) == 1
    assert out_chunks[0] is small
    assert out_counts[0] > 0


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
    monkeypatch.setattr("codesensei.indexing.service.get_embedding_provider", lambda: fake_provider)

    captured = {}

    async def fake_replace_chunks(
        session,
        *,
        repo_id,
        new_chunks,
        embedding_provider,
        embedding_model,
        indexed_at,
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
