"""The Orchestrator: drives the Plan -> Execute -> Verify control loop.

Implements the control loop from the project overview (section 7.2): an initial
plan, then an Executor ReAct loop in which a successful stage_write must pass
the Verifier before it is committed, with explicit termination conditions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import Config, load_config
from ..llm.ollama_client import OllamaClient
from ..mcp.client import FhirMcpClient, McpClientError
from ..trace.langfuse_hook import Tracer
from .executor import call_executor
from .planner import call_planner
from .recovery import recovery_hint
from .state import Action, Plan, ScratchpadEntry
from .verifier import call_verifier

logger = logging.getLogger("medagent.orchestrator")


@dataclass
class AgentResult:
    """The outcome of a full agent run."""

    task: str
    status: str  # "completed" | "aborted"
    final_answer: str
    plan: dict[str, Any] = field(default_factory=dict)
    scratchpad: list[dict[str, Any]] = field(default_factory=list)
    steps_used: int = 0
    abort_reason: str = ""


class Orchestrator:
    """Runs one clinical task end-to-end through the three-layer agent."""

    def __init__(
        self,
        config: Config,
        ollama: OllamaClient,
        mcp: FhirMcpClient,
        tracer: Tracer | None = None,
    ) -> None:
        self._config = config
        self._ollama = ollama
        self._mcp = mcp
        self._tracer = tracer or Tracer(config)

    def run(self, task: str) -> AgentResult:
        """Execute one task. Never raises — failures return an aborted result."""
        with self._tracer.span("agent_run", input=task):
            try:
                return self._run(task)
            except Exception as exc:  # noqa: BLE001 - run() must never raise
                logger.error("agent run failed: %s", exc)
                return AgentResult(
                    task=task, status="aborted", final_answer="",
                    abort_reason=str(exc),
                )

    def _run(self, task: str) -> AgentResult:
        tools = self._mcp.list_tools()

        # --- 1. initial plan ---
        with self._tracer.generation("planner", model=self._config.ollama_model):
            plan = call_planner(self._ollama, task, tools)

        scratchpad: list[ScratchpadEntry] = []
        replans = 0

        # --- 2. Executor ReAct loop ---
        for step in range(1, self._config.max_steps + 1):
            with self._tracer.span(f"iteration_{step}"):
                with self._tracer.generation(
                    "executor", model=self._config.ollama_model
                ):
                    action = call_executor(
                        self._ollama, task, plan, scratchpad, tools,
                        max_retries=self._config.max_retries,
                    )

                if action.type == "task_done":
                    return self._finish(task, plan, scratchpad, step, action)

                if action.type == "step_done":
                    scratchpad.append(self._step_done_entry(action))
                    continue

                if action.type == "replan_request":
                    replans += 1
                    if replans > self._config.max_replans:
                        return self._abort(
                            task, plan, scratchpad, step, "exceeded max replans"
                        )
                    self._tracer.event("replan", reason=action.reason or "")
                    with self._tracer.generation(
                        "replanner", model=self._config.ollama_model
                    ):
                        plan = call_planner(
                            self._ollama, task, tools,
                            replan=True, previous_plan=plan,
                            completed_steps=_done_step_ids(scratchpad),
                            replan_reason=action.reason or "",
                        )
                    continue

                # action.type == "tool_call"
                scratchpad.append(self._handle_tool_call(task, action, scratchpad))

        # --- 3. step-limit termination ---
        return self._abort(
            task, plan, scratchpad, self._config.max_steps, "max_steps reached"
        )

    def _handle_tool_call(
        self, task: str, action: Action, scratchpad: list[ScratchpadEntry]
    ) -> ScratchpadEntry:
        """Run one tool call, including the write gate and error annotation."""
        tool = action.tool or ""
        # program-side guard: commit_write is gated and never called directly
        if tool == "commit_write":
            return self._entry(
                action,
                {"ok": False, "data": None,
                 "error": "commit_write is gated — use stage_write instead"},
            )

        with self._tracer.span(f"tool.{tool}", input=action.args):
            try:
                result = self._mcp.call_tool(tool, action.args)
            except McpClientError as exc:
                result = {"ok": False, "data": None, "error": str(exc)}

        # write gate: a successful stage_write must pass the Verifier
        if tool == "stage_write" and result.get("ok"):
            result = self._verify_and_commit(task, result, scratchpad)

        if not result.get("ok"):
            result = dict(result)
            result["recovery_hint"] = recovery_hint(result.get("error", ""))
        return self._entry(action, result)

    def _verify_and_commit(
        self, task: str, stage_result: dict, scratchpad: list[ScratchpadEntry]
    ) -> dict:
        """Run the Verifier on a staged write; commit only if approved.

        The Verifier also receives the most recent patient-lookup context from
        the scratchpad so it can confirm that a numeric patient_id in the
        staged write corresponds to the named patient in the task — preventing
        false-positive "patient identity mismatch" rejections.
        """
        staged = stage_result.get("data") or {}
        patient_context = _patient_context_from_scratchpad(scratchpad)
        with self._tracer.generation("verifier", model=self._config.ollama_model):
            verdict = call_verifier(
                self._ollama, task, staged, patient_context=patient_context
            )

        if not verdict.approved:
            return {
                "ok": False, "data": staged,
                "error": f"verifier rejected the write: {verdict.reason}",
                "verdict": verdict.model_dump(),
            }

        staged_id = staged.get("staged_id", "")
        with self._tracer.span("tool.commit_write", input={"staged_id": staged_id}):
            commit = self._mcp.call_tool("commit_write", {"staged_id": staged_id})
        commit = dict(commit)
        commit["verdict"] = verdict.model_dump()
        return commit

    # -- scratchpad / result helpers --------------------------------------
    @staticmethod
    def _entry(action: Action, observation: dict) -> ScratchpadEntry:
        return ScratchpadEntry(
            step_id=action.step_id,
            thought=action.thought,
            action=action.model_dump(),
            observation=observation,
            status="done" if observation.get("ok") else "error",
        )

    @staticmethod
    def _step_done_entry(action: Action) -> ScratchpadEntry:
        return ScratchpadEntry(
            step_id=action.step_id,
            thought=action.thought,
            action=action.model_dump(),
            observation={"ok": True, "result_summary": action.result_summary},
            status="done",
        )

    def _finish(
        self, task: str, plan: Plan, scratchpad: list[ScratchpadEntry],
        steps: int, action: Action,
    ) -> AgentResult:
        answer = action.final_answer or ""
        self._tracer.event("final_answer", output=answer)
        return AgentResult(
            task=task, status="completed", final_answer=answer,
            plan=plan.model_dump(),
            scratchpad=[e.model_dump() for e in scratchpad],
            steps_used=steps,
        )

    def _abort(
        self, task: str, plan: Plan, scratchpad: list[ScratchpadEntry],
        steps: int, reason: str,
    ) -> AgentResult:
        logger.warning("agent run aborted: %s", reason)
        return AgentResult(
            task=task, status="aborted", final_answer="",
            plan=plan.model_dump(),
            scratchpad=[e.model_dump() for e in scratchpad],
            steps_used=steps, abort_reason=reason,
        )


def _done_step_ids(scratchpad: list[ScratchpadEntry]) -> list[int]:
    """Step ids that completed successfully — failed steps are not 'done'."""
    return sorted(
        {
            e.step_id
            for e in scratchpad
            if e.step_id is not None and e.status == "done"
        }
    )


def _patient_context_from_scratchpad(scratchpad: list[ScratchpadEntry]) -> str:
    """Build a short patient-identity hint from the most recent find_patient or
    get_patient_summary observation. The Verifier uses this to confirm that a
    numeric patient_id in a staged write maps to the patient named in the task.
    """
    for entry in reversed(scratchpad):
        action = entry.action or {}
        if action.get("tool") not in ("find_patient", "get_patient_summary"):
            continue
        data = (entry.observation or {}).get("data") or {}
        matches = data.get("matches")
        if matches:
            m = matches[0]
            return (
                f"Earlier find_patient matched: name='{m.get('name')}', "
                f"patient_id='{m.get('patient_id')}'"
            )
        if data.get("patient_id"):
            return (
                f"Earlier get_patient_summary: name='{data.get('name')}', "
                f"patient_id='{data.get('patient_id')}'"
            )
    return ""


def build_orchestrator(config: Config | None = None) -> Orchestrator:
    """Construct an Orchestrator with clients built from configuration."""
    cfg = config or load_config()
    ollama = OllamaClient(cfg.ollama_base_url, cfg.ollama_model)
    mcp = FhirMcpClient(cfg.fhir_mcp_url)
    return Orchestrator(cfg, ollama, mcp)
