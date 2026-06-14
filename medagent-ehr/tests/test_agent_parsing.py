"""Unit tests for converting model JSON into agent state objects."""
from medagent.agent.executor import _to_action
from medagent.agent.planner import _to_plan
from medagent.agent.verifier import _to_verdict


def test_to_plan_builds_steps():
    parsed = {
        "task": "t",
        "steps": [
            {"step_id": 1, "intent": "find patient", "expected_tools": ["find_patient"]},
            {"step_id": 2, "intent": "get labs", "depends_on": [1]},
        ],
    }
    plan = _to_plan(parsed, "t")
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == [1]


def test_to_plan_tolerates_missing_fields():
    plan = _to_plan({"steps": [{"intent": "x"}]}, "fallback task")
    assert plan.task == "fallback task"
    assert plan.steps[0].step_id == 1  # auto-numbered


def test_to_action_tool_call():
    action = _to_action(
        {"type": "tool_call", "tool": "find_patient", "args": {"name": "A"}}
    )
    assert action.type == "tool_call"
    assert action.tool == "find_patient"


def test_to_action_bad_type_becomes_replan():
    action = _to_action({"type": "garbage"})
    assert action.type == "replan_request"


def test_to_verdict_approved():
    verdict = _to_verdict(
        {"staged_id": "s1", "verdict": "approved"}, {"staged_id": "s1"}
    )
    assert verdict.approved


def test_to_verdict_bad_value_fails_safe():
    verdict = _to_verdict({"verdict": "maybe"}, {"staged_id": "s1"})
    assert verdict.verdict == "rejected"
