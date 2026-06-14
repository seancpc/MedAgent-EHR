"""Uniform response envelope for all MCP tools.

Every tool returns the same shape so the agent can reason about results
consistently:

    success -> {"ok": True,  "data": <payload>, "error": None}
    failure -> {"ok": False, "data": None,      "error": "<actionable message>"}

Error messages are written to be *actionable*: they should tell the agent what
went wrong and what to try next, e.g.
    "Patient not found for identifier 'X'. Try find_patient with name + birth_date."
"""
from __future__ import annotations

from typing import Any


def ok(data: Any) -> dict[str, Any]:
    """Build a success envelope."""
    return {"ok": True, "data": data, "error": None}


def err(message: str) -> dict[str, Any]:
    """Build a failure envelope. `message` should be actionable for the agent."""
    return {"ok": False, "data": None, "error": message}


def is_ok(envelope: dict[str, Any]) -> bool:
    """True if an envelope represents success."""
    return bool(envelope.get("ok"))
