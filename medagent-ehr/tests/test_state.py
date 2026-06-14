"""Unit tests for the agent state models."""
from medagent.agent.state import Action, Plan, Step, Verdict


def test_plan_round_trip():
    plan = Plan(task="t", steps=[Step(step_id=1, intent="do x")])
    dumped = plan.model_dump()
    assert dumped["steps"][0]["step_id"] == 1
    assert Plan(**dumped).task == "t"


def test_step_defaults():
    step = Step(step_id=1, intent="x")
    assert step.expected_tools == []
    assert step.depends_on == []


def test_action_minimal():
    action = Action(type="task_done", final_answer="done")
    assert action.type == "task_done"
    assert action.tool is None
    assert action.args == {}


def test_verdict_approved_property():
    assert Verdict(staged_id="s", verdict="approved").approved
    assert not Verdict(staged_id="s", verdict="rejected").approved
