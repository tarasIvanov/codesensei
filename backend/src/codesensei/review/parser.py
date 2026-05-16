"""Strict parse of LLM output → (Verdict, list[Finding]). Fail-fast on malformed."""
from __future__ import annotations

import json

from pydantic import ValidationError

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import Finding, Verdict

_FENCE_PREFIXES = ("```json", "```JSON", "```")


def _strip_fences(text: str) -> str:
    body = text.strip()
    for prefix in _FENCE_PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix) :].lstrip("\n").rstrip()
            if body.endswith("```"):
                body = body[: -len("```")].rstrip()
            return body.strip()
    return body


def parse_review(
    provider_name: str, raw: str
) -> tuple[Verdict, list[Finding]]:
    cleaned = _strip_fences(raw)
    if not cleaned:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} returned an empty review.",
        )
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} returned non-JSON output.",
        ) from exc
    if not isinstance(payload, dict):
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} returned JSON that is not an object.",
        )
    if "verdict" not in payload or "findings" not in payload:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} review is missing `verdict` or `findings`.",
        )
    try:
        verdict = Verdict(payload["verdict"])
    except ValueError as exc:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} returned an unknown verdict.",
        ) from exc
    raw_findings = payload["findings"]
    if not isinstance(raw_findings, list):
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
            f"{provider_name} `findings` is not a list.",
        )
    findings: list[Finding] = []
    for entry in raw_findings:
        if not isinstance(entry, dict):
            raise ReviewError(
                ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
                f"{provider_name} returned a non-object finding.",
            )
        try:
            findings.append(Finding(**entry))
        except (ValidationError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first.get("loc", ()))
                reason = f"{loc}: {first.get('msg', 'invalid')}"
            else:
                reason = str(exc)
            raise ReviewError(
                ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT,
                f"{provider_name} finding failed validation ({reason}).",
            ) from exc
    return verdict, findings
