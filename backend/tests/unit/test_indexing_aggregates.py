"""Unit tests for indexing/store.py:get_embedding_token_counts (feature 014)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from codesensei.indexing.store import get_embedding_token_counts


@pytest.mark.asyncio
async def test_empty_repo_ids_returns_empty_dict_without_query():
    """Empty input short-circuits — no DB round-trip."""
    session = SimpleNamespace(execute=AsyncMock())
    result = await get_embedding_token_counts(session, [])
    assert result == {}
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_single_repo_sum_rolls_up_chunks():
    """1 repo + 3 chunks (100/200/300) → {repo.id: 600}."""
    repo_id = uuid4()
    rows = [SimpleNamespace(repo_id=repo_id, total=600)]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)),
    )
    result = await get_embedding_token_counts(session, [repo_id])
    assert result == {repo_id: 600}
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_repos_one_empty_returns_only_non_zero_keys():
    """SQL GROUP BY does not emit a row for repos with zero chunks; caller defaults at the
    enrichment site."""
    r1 = uuid4()
    r2 = uuid4()
    rows = [SimpleNamespace(repo_id=r1, total=300)]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)),
    )
    result = await get_embedding_token_counts(session, [r1, r2])
    assert result == {r1: 300}
    assert r2 not in result


@pytest.mark.asyncio
async def test_null_sum_coerces_to_zero():
    """Defensive: if a row somehow has total=None, we coerce to 0."""
    rid = uuid4()
    rows = [SimpleNamespace(repo_id=rid, total=None)]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)),
    )
    result = await get_embedding_token_counts(session, [rid])
    assert result == {rid: 0}
