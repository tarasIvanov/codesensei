"""Unit tests for the envelope builder in healthcheck.py."""
from codesensei.healthcheck import build_envelope


def test_all_ok_returns_200_and_ok_envelope():
    status, body = build_envelope({"db": "ok", "vector": "ok"}, "ok")
    assert status == 200
    assert body == {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "extensions": {"vector": "ok"},
    }


def test_db_down_returns_503_and_flags_db_and_vector():
    status, body = build_envelope({"db": "down", "vector": "unknown"}, "ok")
    assert status == 503
    assert body["status"] == "degraded"
    assert body["db"] == "down"
    assert body["redis"] == "ok"
    assert body["extensions"]["vector"] == "unknown"
    assert "db" in body["failing"]
    assert "vector" in body["failing"]
    assert "redis" not in body["failing"]


def test_redis_down_returns_503_and_flags_only_redis():
    status, body = build_envelope({"db": "ok", "vector": "ok"}, "down")
    assert status == 503
    assert body["redis"] == "down"
    assert body["failing"] == ["redis"]


def test_vector_missing_returns_503_and_flags_only_vector():
    status, body = build_envelope({"db": "ok", "vector": "missing"}, "ok")
    assert status == 503
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert body["extensions"]["vector"] == "missing"
    assert body["failing"] == ["vector"]


def test_db_and_redis_down_lists_all_failing():
    status, body = build_envelope({"db": "down", "vector": "unknown"}, "down")
    assert status == 503
    assert set(body["failing"]) == {"db", "redis", "vector"}
