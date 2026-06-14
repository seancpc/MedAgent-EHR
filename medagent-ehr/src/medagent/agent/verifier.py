"""The Verifier: the safety gate before a staged write is committed.

Runs with thinking ON. Fails safe: an unparseable verdict is treated as a
rejection.
"""
from __future__ import annotations

import json

from ..llm import templates
from ..llm.ollama_client import OllamaClient
from .state import Verdict


def call_verifier(
    ollama: OllamaClient,
    task: str,
    staged_write: dict,
    *,
    patient_context: str = "",
) -> Verdict:
    """Ask the verifier whether a staged write may be committed."""
    system, user = templates.render(
        "verifier.j2",
        task=task,
        staged_write=json.dumps(staged_write, ensure_ascii=False),
        patient_context=patient_context,
    )
    # think=False for v1 (same reasoning as planner): a binary approve/reject
    # decision doesn't need deep CoT in practice.
    parsed, _result = ollama.chat_json(system, user, think=False)
    return _to_verdict(parsed, staged_write)


def _to_verdict(parsed: dict, staged_write: dict) -> Verdict:
    """Build a Verdict; an unrecognized verdict fails safe to a rejection."""
    staged_id = str(parsed.get("staged_id") or staged_write.get("staged_id", ""))
    verdict_value = parsed.get("verdict")
    if verdict_value not in ("approved", "rejected"):
        return Verdict(
            staged_id=staged_id,
            verdict="rejected",
            reason=f"verifier returned an unrecognized verdict: {verdict_value!r}",
        )
    return Verdict(
        staged_id=staged_id,
        verdict=verdict_value,
        reason=parsed.get("reason", ""),
        checks=parsed.get("checks") or {},
    )
