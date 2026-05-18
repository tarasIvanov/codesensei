"""FastAPI route — POST /api/review/post."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.posting.schema import PostReviewRequest
from codesensei.posting.service import post_review_to_github

router = APIRouter(tags=["posting"])


@router.post("/review/post")
async def post_review(req: PostReviewRequest) -> JSONResponse:
    receipt = await post_review_to_github(req)
    return JSONResponse(status_code=200, content=receipt.model_dump(mode="json"))
