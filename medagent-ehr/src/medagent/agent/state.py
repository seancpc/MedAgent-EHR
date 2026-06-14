"""Typed data structures exchanged between the agent's three layers.

These Pydantic models are the contracts described in the project overview
(sections 5.3 and 7.1.4): the Planner emits a Plan, the Executor emits an
Action each turn, and the Verifier emits a Verdict.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Planner output ------------------------------------------------------
class Step(BaseModel):
    """One step in a plan — an intent, not a fixed instruction."""

    step_id: int
    intent: str
    expected_tools: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)


class Plan(BaseModel):
    """An ordered, dependency-aware decomposition of the user task."""

    task: str
    steps: list[Step] = Field(default_factory=list)


# --- Executor output -----------------------------------------------------
ActionType = Literal["tool_call", "step_done", "task_done", "replan_request"]


class Action(BaseModel):
    """A single action chosen by the Executor for the current turn."""

    type: ActionType
    step_id: int | None = None
    thought: str = ""
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    final_answer: str | None = None
    reason: str | None = None


# --- Executor scratchpad -------------------------------------------------
class ScratchpadEntry(BaseModel):
    """One recorded step of the Executor's ReAct loop."""

    step_id: int | None = None
    thought: str = ""
    action: dict[str, Any] = Field(default_factory=dict)
    observation: dict[str, Any] = Field(default_factory=dict)
    status: str = "done"


# --- Verifier output -----------------------------------------------------
VerdictType = Literal["approved", "rejected"]


class Verdict(BaseModel):
    """The Verifier's decision on a staged write."""

    staged_id: str
    verdict: VerdictType
    reason: str = ""
    checks: dict[str, str] = Field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.verdict == "approved"
