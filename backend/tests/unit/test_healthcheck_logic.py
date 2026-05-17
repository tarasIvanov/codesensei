"""Unit tests for the envelope builder in healthcheck.py."""
from codesensei.healthcheck import build_envelope
from codesensei.providers.base import ProviderState


def _ok_providers():
    return ProviderState.OK, ProviderState.OK


def test_all_ok_returns_200_and_ok_envelope():
    status, body = build_envelope(
        {"db": "ok", "vector": "ok"}, "ok", *_ok_providers(), worker_state="ok"
    )
    assert status == 200
    assert body == {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "extensions": {"vector": "ok"},
        "providers": {"llm": "ok", "embedding": "ok"},
        "worker": "ok",
    }


def test_db_down_returns_503_and_flags_db_and_vector():
    status, body = build_envelope(
        {"db": "down", "vector": "unknown"}, "ok", *_ok_providers(), worker_state="ok"
    )
    assert status == 503
    assert body["status"] == "degraded"
    assert body["db"] == "down"
    assert body["redis"] == "ok"
    assert body["extensions"]["vector"] == "unknown"
    assert "db" in body["failing"]
    assert "vector" in body["failing"]
    assert "redis" not in body["failing"]
    assert body["providers"] == {"llm": "ok", "embedding": "ok"}
    assert body["worker"] == "ok"


def test_redis_down_returns_503_and_flags_only_redis():
    status, body = build_envelope(
        {"db": "ok", "vector": "ok"}, "down", *_ok_providers(), worker_state="ok"
    )
    assert status == 503
    assert body["redis"] == "down"
    assert body["failing"] == ["redis"]


def test_vector_missing_returns_503_and_flags_only_vector():
    status, body = build_envelope(
        {"db": "ok", "vector": "missing"}, "ok", *_ok_providers(), worker_state="ok"
    )
    assert status == 503
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert body["extensions"]["vector"] == "missing"
    assert body["failing"] == ["vector"]


def test_db_and_redis_down_lists_all_failing():
    status, body = build_envelope(
        {"db": "down", "vector": "unknown"}, "down", *_ok_providers(), worker_state="ok"
    )
    assert status == 503
    assert set(body["failing"]) == {"db", "redis", "vector"}


def test_provider_states_do_not_affect_overall_status_or_failing():
    """FR-013: provider states are informational."""
    status, body = build_envelope(
        {"db": "ok", "vector": "ok"},
        "ok",
        ProviderState.UNCONFIGURED,
        ProviderState.UNREACHABLE,
        worker_state="ok",
    )
    assert status == 200
    assert body["status"] == "ok"
    assert body["providers"] == {"llm": "unconfigured", "embedding": "unreachable"}
    assert "failing" not in body


def test_worker_state_does_not_affect_overall_status_or_failing():
    """FR-005: worker state is informational, never gates overall."""
    for state in ("ok", "down", "unreachable"):
        status, body = build_envelope(
            {"db": "ok", "vector": "ok"}, "ok", *_ok_providers(), worker_state=state
        )
        assert status == 200
        assert body["status"] == "ok"
        assert body["worker"] == state
        assert "failing" not in body


def test_worker_state_default_is_unreachable():
    status, body = build_envelope({"db": "ok", "vector": "ok"}, "ok", *_ok_providers())
    assert body["worker"] == "unreachable"
