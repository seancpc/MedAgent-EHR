"""The Planner: decomposes a clinical task into an ordered Plan.

Runs with thinking ON. Can also revise an existing plan (replan mode).
"""
from __future__ import annotations

from ..llm import templates
from ..llm.ollama_client import OllamaClient
from .state import Plan, Step


def _tools_summary(tools: list[dict]) -> str:
    """One line per tool for the planner prompt."""
    return "\n".join(f"- {t['name']}: {t['description']}" for t in tools)


def call_planner(
    ollama: OllamaClient,
    task: str,
    tools: list[dict],
    *,
    patient_context: str = "",
    replan: bool = False,
    previous_plan: Plan | None = None,
    completed_steps: list[int] | None = None,
    replan_reason: str = "",
) -> Plan:
    """Produce a Plan for `task`. Set replan=True to revise an existing plan."""
    system, user = templates.render(
        "planner.j2",
        available_tools=_tools_summary(tools),
        task=task,
        patient_context=patient_context,
        replan=replan,
        previous_plan=previous_plan.model_dump_json() if previous_plan else "",
        completed_steps=completed_steps or [],
        replan_reason=replan_reason,
    )
    # think=False for v1: Qwen3.6 thinking can run away on multi-step plans;
    # plain decomposition is fast and good enough. Re-enable later to study.
    parsed, _result = ollama.chat_json(system, user, think=False)
    return _to_plan(parsed, task)


def _to_plan(parsed: dict, task: str) -> Plan:
    """Build a validated Plan from the model's JSON, tolerating minor variation."""
    steps: list[Step] = []
    for i, raw in enumerate(parsed.get("steps", []) or [], start=1):
        steps.append(
            Step(
                step_id=raw.get("step_id", i),
                intent=raw.get("intent", ""),
                expected_tools=raw.get("expected_tools") or [],
                depends_on=raw.get("depends_on") or [],
            )
        )
    return Plan(task=parsed.get("task") or task, steps=steps)
