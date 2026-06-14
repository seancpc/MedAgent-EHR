"""Adapter between MedAgentBench tasks and the medagent-ehr agent.

Loads MedAgentBench's task set into agent-ready `BenchmarkTask` objects and
grades agent runs.

GRADING
-------
MedAgentBench's official per-category graders live in `refsol.py`, distributed
via a login-gated Stanford Box folder. When that file is present at
`benchmark/medagentbench_official/refsol.py` (with its `utils.py` dependency,
and the `requests` package installed), this adapter delegates grading to the
official graders. When it is absent, grading falls back to a builtin check for
category `task1` and `ungraded` for the rest.

How the official graders are driven
-----------------------------------
The refsol graders expect MedAgentBench's own result object: `.result` (a JSON
list string) and `.history` (messages with `.role`/`.content`, from which write
tasks scrape `POST` request payloads). The medagent-ehr agent produces a
different `AgentResult`, so `_to_medagentbench_result()` shims one into the
other:
  * `.result`  <- the agent's final answer (best-effort JSON-array extraction);
  * `.history` <- reconstructed POST entries, one per committed stage_write,
                  built from each scratchpad entry's `fhir_resource` payload.

NOTE ON EXPECTED SCORES: the official write-task graders assert very specific
FHIR payload shapes. The medagent-ehr agent's payloads (built by fhir-mcp-server)
will not all match out of the box — closing that gap is agent/builder tuning,
i.e. the real benchmark work, not an adapter defect.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

OFFICIAL_GRADER_NOTE = (
    "MedAgentBench's official graders (refsol.py) ship via a login-gated "
    "Stanford Box folder. Place refsol.py + utils.py in "
    "benchmark/medagentbench_official/ and install `requests` to enable "
    "full grading."
)

# Appended to every task so the agent answers in MedAgentBench's list format.
_ANSWER_FORMAT = (
    "\n\nIMPORTANT — finish by giving the final answer as a compact JSON array, "
    'matching MedAgentBench format. Examples: ["S6534835"] for an MRN, [67] for '
    "a number, [-1] when a value is unavailable, [] when only an action was "
    "required. Return ONLY the value(s) the question asks for — do not add a "
    "timestamp unless the question explicitly asks when it was recorded."
)

# Targeted format hint for task10 only (its answer is value + when-recorded).
_TASK10_FORMAT = (
    " For THIS task specifically, the answer is two elements [value, timestamp]: "
    "the last HbA1C value and the exact effectiveDateTime string it was recorded "
    'at, copied verbatim (e.g. [6.6, "2023-11-04T14:54:00+00:00"]). '
    "Use [-1] only if no measurement exists."
)


@dataclass
class BenchmarkTask:
    """One MedAgentBench task in agent-ready form."""

    task_id: str           # e.g. "task1_1"
    category: str          # e.g. "task1" — the prefix that selects the grader
    instruction: str       # instruction + context + answer-format directive
    eval_mrn: str          # patient MRN the official grader queries
    sol: list[Any]         # reference answer (present for task1; [] otherwise)
    raw: dict[str, Any]    # the original task object — passed to refsol as case_data


def load_tasks(path: str) -> list[BenchmarkTask]:
    """Load MedAgentBench tasks from a `test_data_v*.json` file.

    The file is a JSON array of objects with keys: id, instruction, context,
    eval_MRN, and (category task1 only) sol.
    """
    raw_tasks = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw_tasks, list):
        raise ValueError(f"{path}: expected a JSON array of task objects")

    tasks: list[BenchmarkTask] = []
    for obj in raw_tasks:
        task_id = obj["id"]
        category = task_id.split("_")[0]
        instruction = obj.get("instruction", "")
        context = obj.get("context", "")
        full = instruction if not context else f"{instruction}\n\n{context}"
        full += _ANSWER_FORMAT
        # task10 is the only category whose answer is [value, timestamp]; give it
        # a targeted format hint so other categories keep returning [value].
        if category == "task10":
            full += _TASK10_FORMAT
        tasks.append(
            BenchmarkTask(
                task_id=task_id,
                category=category,
                instruction=full,
                eval_mrn=obj.get("eval_MRN", ""),
                sol=obj.get("sol", []) or [],
                raw=obj,
            )
        )
    return tasks


# --- result shim: AgentResult -> MedAgentBench-shaped result object ------
@dataclass
class _HistoryItem:
    """A MedAgentBench history message — refsol reads `.role` and `.content`."""

    role: str
    content: str


@dataclass
class _ShimResult:
    """A MedAgentBench result object — refsol reads `.result` and `.history`."""

    result: str
    history: list[_HistoryItem] = field(default_factory=list)


def _extract_result_string(final_answer: str) -> str:
    """Best-effort turn the agent's final answer into a JSON-array string."""
    text = (final_answer or "").strip()
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass
    return text  # leave it; refsol's json.loads will fail it honestly


def _build_history(scratchpad: list[dict], fhir_api_base: str) -> list[_HistoryItem]:
    """Reconstruct MedAgentBench-style POST history from the agent scratchpad.

    For each committed stage_write, emit the `POST <url>\\n<json>` agent message
    followed by an acceptance message — the pair shape refsol's extract_posts
    expects.
    """
    history: list[_HistoryItem] = []
    for entry in scratchpad:
        action = entry.get("action") or {}
        data = (entry.get("observation") or {}).get("data") or {}
        if (
            action.get("tool") == "stage_write"
            and data.get("committed")
            and data.get("fhir_resource")
        ):
            resource = data["fhir_resource"]
            url = f"{fhir_api_base}{resource.get('resourceType', '')}"
            history.append(
                _HistoryItem("agent", f"POST {url}\n{json.dumps(resource)}")
            )
            history.append(
                _HistoryItem("user", "POST request accepted and executed successfully")
            )
    return history


def _to_medagentbench_result(agent_result: Any, fhir_api_base: str) -> _ShimResult:
    """Shim an AgentResult into the result object refsol graders expect."""
    final_answer = getattr(agent_result, "final_answer", "") or ""
    scratchpad = getattr(agent_result, "scratchpad", []) or []
    return _ShimResult(
        result=_extract_result_string(final_answer),
        history=_build_history(scratchpad, fhir_api_base),
    )


# --- grading -------------------------------------------------------------
GradeOutcome = Literal["pass", "fail", "ungraded"]


@dataclass
class GradeResult:
    """Outcome of grading one task."""

    outcome: GradeOutcome
    detail: str = ""

    @property
    def is_pass(self) -> bool:
        return self.outcome == "pass"


_refsol_module: Any = "unset"


def _load_refsol() -> Any:
    """Import the official refsol grader module, or None if unavailable."""
    global _refsol_module
    if _refsol_module == "unset":
        try:
            from medagentbench_official import refsol as _refsol

            _refsol_module = _refsol
        except Exception:  # missing refsol.py, or missing `requests`, etc.
            _refsol_module = None
    return _refsol_module


def refsol_available() -> bool:
    """True if the official MedAgentBench graders (refsol.py) are importable."""
    return _load_refsol() is not None


def grade(task: BenchmarkTask, agent_result: Any, fhir_api_base: str = "") -> GradeResult:
    """Grade one agent run.

    Delegates to MedAgentBench's official refsol graders when available;
    otherwise grades category `task1` with a builtin check and returns
    `ungraded` for the rest.
    """
    refsol = _load_refsol()
    if refsol is not None:
        return _grade_via_refsol(refsol, task, agent_result, fhir_api_base)
    if task.category == "task1":
        return _grade_task1(task, getattr(agent_result, "final_answer", "") or "")
    return GradeResult("ungraded", f"{task.category}: {OFFICIAL_GRADER_NOTE}")


def _grade_via_refsol(
    refsol: Any, task: BenchmarkTask, agent_result: Any, fhir_api_base: str
) -> GradeResult:
    """Grade by delegating to the official refsol per-category grader."""
    if not fhir_api_base:
        return GradeResult(
            "ungraded",
            f"{task.category}: official grading needs a FHIR base URL "
            "(pass --fhir-api-base to run_medagentbench.py)",
        )
    grader = getattr(refsol, task.category, None)
    if grader is None:
        return GradeResult("ungraded", f"refsol has no grader for {task.category}")
    shimmed = _to_medagentbench_result(agent_result, fhir_api_base)
    try:
        passed = grader(task.raw, shimmed, fhir_api_base)
    except Exception as exc:  # refsol graders can raise on unexpected shapes
        return GradeResult("fail", f"refsol.{task.category} raised: {exc}")
    if passed is True:
        return GradeResult("pass", f"official refsol.{task.category} passed")
    return GradeResult("fail", f"official refsol.{task.category} returned {passed!r}")


def _grade_task1(task: BenchmarkTask, final_answer: str) -> GradeResult:
    """Builtin fallback grader for category task1 (used only when refsol absent).

    task1's reference answer ships in the public data as `sol`. Pass if every
    reference value appears in the agent's final answer.
    """
    answer = (final_answer or "").strip()
    if not answer:
        return GradeResult("fail", "agent produced no final answer")
    if not task.sol:
        return GradeResult("ungraded", "task1 task has no reference 'sol'")
    missing = [str(v) for v in task.sol if str(v) not in answer]
    if missing:
        return GradeResult(
            "fail", f"reference value(s) {missing} not found in answer: {answer!r}"
        )
    return GradeResult("pass", f"answer contains reference {task.sol}")
