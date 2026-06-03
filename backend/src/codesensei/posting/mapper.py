"""ReviewResult → GitHub Reviews API payload.

Pure transformation. Splits findings into inline-pool (file + line ≥ 1) and
body-pool (locationless). Caps inline pool at INLINE_COMMENT_CAP; overflow
joins the body bullets. See contracts/github_review_payload.md.
"""

from __future__ import annotations

from codesensei.review.schema import Finding, ReviewResult

INLINE_COMMENT_CAP = 50
SIDE = "RIGHT"


def _has_location(finding: Finding) -> bool:
    return bool(finding.file) and isinstance(finding.line, int) and finding.line >= 1


def _render_inline_body(finding: Finding) -> str:
    head = f"**{finding.severity.value}**: {finding.message}"
    if finding.suggestion:
        return f"{head}\n\n_Suggestion_: {finding.suggestion}"
    return head


def _render_bullet(finding: Finding, *, include_location: bool) -> str:
    sev = finding.severity.value
    if include_location:
        head = f"- **{sev}** at `{finding.file}:{finding.line}`: {finding.message}"
    else:
        head = f"- **{sev}**: {finding.message}"
    if finding.suggestion:
        return f"{head}  \n  _Suggestion_: {finding.suggestion}"
    return head


def _build_inline_comment(finding: Finding) -> dict[str, object]:
    return {
        "path": finding.file,
        "side": SIDE,
        "line": finding.line,
        "body": _render_inline_body(finding),
    }


def _compose_top_body(
    review: ReviewResult,
    *,
    locationless: list[Finding],
    overflow: list[Finding],
) -> str:
    parts: list[str] = []
    if locationless:
        parts.extend(
            ["### Findings without inline location"]
            + [_render_bullet(f, include_location=False) for f in locationless]
        )
    if overflow:
        if parts:
            parts.append("")
        parts.extend(
            ["### Additional findings (beyond the 50-comment cap)"]
            + [_render_bullet(f, include_location=True) for f in overflow]
        )
    return "\n".join(parts)


def build_payload(review_result: ReviewResult, event: str) -> dict[str, object]:
    """Return GitHub Reviews API request body for the given ReviewResult."""
    inline_pool: list[Finding] = []
    locationless: list[Finding] = []
    for finding in review_result.findings:
        if _has_location(finding):
            inline_pool.append(finding)
        else:
            locationless.append(finding)

    inline_capped = inline_pool[:INLINE_COMMENT_CAP]
    overflow = inline_pool[INLINE_COMMENT_CAP:]
    comments = [_build_inline_comment(f) for f in inline_capped]
    body = _compose_top_body(review_result, locationless=locationless, overflow=overflow)
    return {"event": event, "body": body, "comments": comments}
