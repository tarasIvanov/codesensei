"""HTTP endpoints for repo indexing + registry (filled progressively across T019/T020/T037)."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Request, Response, status

from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.service import IndexingService

router = APIRouter(tags=["indexing"])
_logger = structlog.get_logger()


@router.post("/index", status_code=status.HTTP_201_CREATED)
async def post_index(request: Request) -> Response:
    """Dispatch sync (≤200 source files) or async (>200) indexing."""
    payload = await request.json()
    if not isinstance(payload, dict):
        raise IndexError(IndexErrorCategory.INVALID_INPUT, "Body must be a JSON object.")
    source = payload.get("source")
    default_branch = payload.get("default_branch")
    if not isinstance(source, str) or not source.strip():
        raise IndexError(IndexErrorCategory.INVALID_INPUT, "Field 'source' is required.")
    if default_branch is not None and not isinstance(default_branch, str):
        raise IndexError(
            IndexErrorCategory.INVALID_INPUT, "Field 'default_branch' must be a string."
        )

    service = IndexingService.from_request()
    result = await service.dispatch(source=source, default_branch=default_branch)
    status_code = 201 if result["mode"] == "sync" else 202
    return Response(
        content=__import__("json").dumps(result),
        media_type="application/json",
        status_code=status_code,
    )


@router.get("/repos")
async def list_repos() -> dict[str, list[dict[str, object]]]:
    service = IndexingService.from_request()
    rows = await service.list_repos()
    return {"repos": rows}


@router.delete("/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(repo_id: UUID) -> Response:
    service = IndexingService.from_request()
    await service.delete_repo(repo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
