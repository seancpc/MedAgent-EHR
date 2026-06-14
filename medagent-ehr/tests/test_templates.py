"""Unit tests for prompt template rendering."""
from medagent.llm import templates


def test_planner_template_renders():
    system, user = templates.render(
        "planner.j2",
        available_tools="- find_patient: find a patient",
        task="find patient John",
        patient_context="",
        replan=False,
        previous_plan="",
        completed_steps=[],
        replan_reason="",
    )
    assert "PLANNER" in system
    assert "find patient John" in user


def test_executor_template_renders():
    system, user = templates.render(
        "executor.j2",
        tools="- find_patient: ...",
        max_retries=3,
        task="some task",
        plan="{}",
        scratchpad="(nothing done yet)",
    )
    assert "EXECUTOR" in system
    assert "some task" in user


def test_verifier_template_renders():
    system, user = templates.render(
        "verifier.j2",
        task="some task",
        staged_write="{}",
        patient_context="",
    )
    assert "VERIFIER" in system
    assert "some task" in user
