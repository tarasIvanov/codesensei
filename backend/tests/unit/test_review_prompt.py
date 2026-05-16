"""US1: Prompt snapshot — guards against accidental edits to the LLM contract."""
from __future__ import annotations

from codesensei.review.prompt import SYSTEM_MESSAGE, USER_TEMPLATE, build_messages


def test_system_message_starts_with_role():
    assert SYSTEM_MESSAGE.startswith("You are a senior code reviewer.")


def test_system_message_pins_json_envelope():
    must_contain = [
        '"verdict": "approve" | "request_changes" | "comment"',
        '"findings": [',
        '"severity": "blocker" | "major" | "minor" | "nit"',
        "Output ONLY a single JSON object",
    ]
    for needle in must_contain:
        assert needle in SYSTEM_MESSAGE, f"missing pin: {needle!r}"


def test_system_message_pins_verdict_rules():
    assert 'verdict is "request_changes"' in SYSTEM_MESSAGE
    assert 'verdict is "comment"' in SYSTEM_MESSAGE
    assert 'verdict is "approve"' in SYSTEM_MESSAGE


def test_user_template_wraps_in_diff_fence():
    out = USER_TEMPLATE.format(DIFF="SAMPLE_DIFF")
    assert "```diff\nSAMPLE_DIFF\n```" in out


def test_build_messages_produces_two_roles():
    msgs = build_messages("diff --git a/x b/x\n")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == SYSTEM_MESSAGE
    assert "```diff" in msgs[1]["content"]
    assert "diff --git a/x b/x" in msgs[1]["content"]
