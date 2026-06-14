"""The Executor: decides the single next Action given the plan and progress.

Runs with thinking OFF to save cost; the ReAct recovery strategy is supplied in
the prompt rather than left to free reasoning.
"""
from __future__ import annotations

import json

from ..llm import templates
from ..llm.ollama_client import OllamaClient
from .state import Action, Plan, ScratchpadEntry

_VALID_TYPES = ("tool_call", "step_done", "task_done", "replan_request")


def _tools_spec(tools: list[dict]) -> str:
    """Full tool spec (name, description, arg names) for the executor prompt."""
    lines: list[str] = []
    for t in tools:
        lines.append(f"- {t['name']}: {t['description']}")
        props = (t.get("input_schema") or {}).get("properties")
        if props:
            lines.append(f"    args: {', '.join(props.keys())}")
    return "\n".join(lines)


def _scratchpad_text(scratchpad: list[ScratchpadEntry]) -> str:
    if not scratchpad:
        return "(nothing done yet)"
    return json.dumps([e.model_dump() for e in scratchpad], ensure_ascii=False)


def call_executor(
    ollama: OllamaClient,
    task: str,
    plan: Plan,
    scratchpad: list[ScratchpadEntry],
    tools: list[dict],
    *,
    max_retries: int = 3,
) -> Action:
    """Ask the executor for the next action."""
    system, user = templates.render(
        "executor.j2",
        tools=_tools_spec(tools),
        max_retries=max_retries,
        task=task,
        plan=plan.model_dump_json(),
        scratchpad=_scratchpad_text(scratchpad),
    )
    parsed, _result = ollama.chat_json(system, user, think=False)
    return _to_action(parsed)


def _coerce_str(value: object | None) -> str | None:
    """Keep strings; serialize list/dict to JSON; pass None through.

    The LLM sometimes produces `final_answer` as a JSON array (because we ask
    for MedAgentBench list format) instead of a string-of-array. We store the
    JSON-encoded text so Action's string-typed field stays valid; downstream
    (the benchmark shim's _extract_result_string) parses it back.
    """
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _to_action(parsed: dict) -> Action:
    """Build a validated Action; an unrecognized type becomes a replan_request."""
    action_type = parsed.get("type")
    if action_type not in _VALID_TYPES:
        return Action(
            type="replan_request",
            reason=f"executor returned an unrecognized action type: {action_type!r}",
        )
    return Action(
        type=action_type,
        step_id=parsed.get("step_id"),
        thought=parsed.get("thought", ""),
        tool=parsed.get("tool"),
        args=parsed.get("args") or {},
        result_summary=_coerce_str(parsed.get("result_summary")),
        final_answer=_coerce_str(parsed.get("final_answer")),
        reason=_coerce_str(parsed.get("reason")),
    )
