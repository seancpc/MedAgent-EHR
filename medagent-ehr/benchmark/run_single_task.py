"""Run ONE MedAgentBench task and dump the full agent trace to JSON.

The benchmark runner only saves grades and step counts; this tool saves the
whole trajectory — plan, every thought/tool call/observation, and the
Verifier verdict on each staged write — so a single run can serve as
documentary evidence (e.g. "the Verifier rejected a bad write, the agent
corrected it, then the commit passed").

Usage (desktop, with llama-server + FHIR + MCP running):
    python medagent-ehr/benchmark/run_single_task.py test_data_v2.json \\
        --task-id task8_1 --out trace_task8_1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                  # benchmark/ -> adapter
sys.path.insert(0, str(_HERE.parent / "src"))   # ../src     -> medagent
import adapter  # noqa: E402

from medagent.agent.orchestrator import build_orchestrator  # noqa: E402


def _verifier_events(scratchpad: list[dict]) -> list[dict]:
    """Pull out every stage_write step and what the Verifier did with it."""
    events = []
    for i, entry in enumerate(scratchpad, 1):
        action = entry.get("action") or {}
        if action.get("tool") != "stage_write":
            continue
        obs = entry.get("observation") or {}
        verdict = obs.get("verdict") or {}
        error = obs.get("error", "")
        if obs.get("ok"):
            outcome = "APPROVED + COMMITTED"
        elif "verifier rejected" in str(error):
            outcome = "REJECTED BY VERIFIER"
        else:
            outcome = f"FAILED ({error[:80]})" if error else "FAILED"
        events.append({
            "step": i,
            "outcome": outcome,
            "verdict_reason": verdict.get("reason", ""),
            "error": error,
        })
    return events


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run one task, dump full trace")
    parser.add_argument("tasks_path", help="Path to MedAgentBench test_data_v2.json")
    parser.add_argument("--task-id", required=True, help="e.g. task8_1")
    parser.add_argument("--out", default="", help="trace JSON path (default: <task-id>_trace.json)")
    args = parser.parse_args()

    tasks = adapter.load_tasks(args.tasks_path)
    task = next((t for t in tasks if t.task_id == args.task_id), None)
    if task is None:
        print(f"error: task_id '{args.task_id}' not found", file=sys.stderr)
        return 2

    print(f"running {task.task_id} ({task.category}) ...")
    orchestrator = build_orchestrator()
    result = orchestrator.run(task.instruction)

    trace = {
        "task_id": task.task_id,
        "category": task.category,
        "instruction": task.instruction,
        "status": result.status,
        "steps_used": result.steps_used,
        "abort_reason": result.abort_reason,
        "final_answer": result.final_answer,
        "plan": result.plan,
        "scratchpad": result.scratchpad,
        "verifier_events": _verifier_events(result.scratchpad),
    }

    out = Path(args.out or f"{task.task_id}_trace.json")
    out.write_text(
        json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"status={result.status}  steps={result.steps_used}")
    print(f"final_answer: {result.final_answer[:200]}")
    if trace["verifier_events"]:
        print("verifier events:")
        for ev in trace["verifier_events"]:
            reason = f" — {ev['verdict_reason']}" if ev["verdict_reason"] else ""
            print(f"  step {ev['step']}: {ev['outcome']}{reason}")
    else:
        print("verifier events: none (no stage_write in this run)")
    print(f"full trace -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
