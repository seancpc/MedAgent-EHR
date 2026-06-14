"""Graded error-recovery helpers for the Executor loop.

The Executor prompt instructs the LLM how to recover from tool failures; this
module backs that with program-side classification. When a tool fails, the
orchestrator tags the observation with a recovery hint so the executor's next
turn gets a clear, category-specific nudge.
"""
from __future__ import annotations

# error category -> short recovery hint surfaced back to the executor
RECOVERY_HINTS = {
    "code_resolution": "code resolution failed — retry resolve_code with a clearer term",
    "empty_result": "nothing found — widen the date range or conclude 'no data'",
    "transient": "transient error — the same action may be retried",
    "validation": "input was rejected — re-examine the values; do not force it",
    "unknown": "the tool returned an error — review the call and adjust",
}


def classify_error(error_message: str) -> str:
    """Classify a tool error message into a recovery category."""
    msg = (error_message or "").lower()
    if "resolve" in msg:
        return "code_resolution"
    if any(
        kw in msg
        for kw in ("exceeds", "invalid", "missing required", "not numeric",
                   "outside the plausible range")
    ):
        return "validation"
    if "not found" in msg or "no staged write" in msg or "empty" in msg:
        return "empty_result"
    if any(kw in msg for kw in ("failed after", "unreachable", "timeout")):
        return "transient"
    return "unknown"


def recovery_hint(error_message: str) -> str:
    """Return the recovery hint for a given tool error message."""
    return RECOVERY_HINTS[classify_error(error_message)]
