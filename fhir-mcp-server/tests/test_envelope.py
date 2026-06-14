"""Unit tests for the response envelope."""
from fhir_mcp.envelope import err, is_ok, ok


def test_ok_envelope():
    env = ok({"value": 1})
    assert env == {"ok": True, "data": {"value": 1}, "error": None}
    assert is_ok(env)


def test_err_envelope():
    env = err("something went wrong")
    assert env == {"ok": False, "data": None, "error": "something went wrong"}
    assert not is_ok(env)


def test_is_ok_handles_missing_key():
    assert not is_ok({})
