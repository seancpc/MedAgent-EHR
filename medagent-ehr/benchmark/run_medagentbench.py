"""Run the medagent-ehr agent over the MedAgentBench task set.

`adapter.load_tasks()` is fully implemented. `adapter.grade()` delegates to
MedAgentBench's official graders when `refsol.py` is present (see adapter.py and
benchmark/medagentbench_official/); otherwise it grades only category task1.

Point fhir-mcp-server's FHIR_BASE_URL at MedAgentBench's own FHIR dataset (the
HAPI server from Docker image `jyxsu6/medagentbench:latest`) so the eval_MRN
patients exist, and pass that same FHIR base URL via --fhir-api-base so the
official graders can query it.

Usage:
    python benchmark/run_medagentbench.py <test_data_v2.json> \\
        --fhir-api-base http://localhost:8080/fhir/ [--out results/run.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

# benchmark/ is a plain scripts directory; allow importing sibling modules
# (adapter) and the medagent package from src/ without requiring an editable
# install or an activated venv.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                  # benchmark/ -> adapter
sys.path.insert(0, str(_HERE.parent / "src"))   # ../src     -> medagent
import adapter  # noqa: E402

from medagent.agent.orchestrator import build_orchestrator  # noqa: E402


def _summarize(total: int, records: list[dict]) -> dict:
    """Build the result summary from the records collected so far."""
    passed = sum(1 for r in records if r["grade"] == "pass")
    failed = sum(1 for r in records if r["grade"] == "fail")
    ungraded = sum(1 for r in records if r["grade"] == "ungraded")
    graded_total = passed + failed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "ungraded": ungraded,
        "pass_rate_over_graded": (
            round(passed / graded_total, 4) if graded_total else 0.0
        ),
        "records": records,
    }


def _run_with_timeout(orchestrator, instruction: str, timeout: float):
    """Run one task with a wall-clock cap.

    Returns the AgentResult, or None if the task exceeded `timeout`. On timeout
    the worker thread is left to unwind on its own (it ends when the in-flight
    LLM request returns or hits its own 600s HTTP timeout); the main loop moves
    on to the next task immediately. Windows has no signal.alarm, so a worker
    thread is the portable way to bound wall-clock time.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(orchestrator.run, instruction)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout:
        return None
    finally:
        executor.shutdown(wait=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MedAgentBench with the medagent-ehr agent."
    )
    parser.add_argument("tasks_path", help="Path to MedAgentBench test_data_v2.json")
    parser.add_argument(
        "--fhir-api-base",
        default="http://localhost:8080/fhir/",
        help="FHIR base URL the official graders query (must end with '/')",
    )
    parser.add_argument("--out", default="benchmark/results/run.json")
    parser.add_argument(
        "--per-task-timeout",
        type=float,
        default=900.0,
        help="Max wall-clock seconds for one task. On timeout the task is "
        "recorded as failed and the run continues to the next task. Default 900.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tasks already present in --out and run only the rest, "
        "merging new results into the existing file.",
    )
    args = parser.parse_args()

    if not adapter.refsol_available():
        print(
            "WARNING: official refsol.py not found — only task1 is graded; "
            "task2..task9 will be 'ungraded'. See benchmark/medagentbench_official/.",
            file=sys.stderr,
        )

    tasks = adapter.load_tasks(args.tasks_path)
    orchestrator = build_orchestrator()
    out = Path(args.out)
    total = len(tasks)

    # --- resume: keep records already in --out, skip those task_ids ---
    records: list[dict] = []
    done_ids: set[str] = set()
    if args.resume and out.exists():
        prior = json.loads(out.read_text(encoding="utf-8"))
        records = list(prior.get("records", []))
        done_ids = {r["task_id"] for r in records}
        print(
            f"  resume: {len(done_ids)} task(s) already in {out}, skipping them",
            file=sys.stderr,
        )

    def checkpoint() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(_summarize(total, records), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    try:
        for i, task in enumerate(tasks, 1):
            if task.task_id in done_ids:
                print(f"  [{i}/{total}] {task.task_id}: skip (done)", file=sys.stderr)
                continue

            result = _run_with_timeout(
                orchestrator, task.instruction, args.per_task_timeout
            )
            if result is None:
                records.append(
                    {
                        "task_id": task.task_id,
                        "category": task.category,
                        "status": "timeout",
                        "grade": "fail",
                        "grade_detail": (
                            f"per-task timeout exceeded "
                            f"(>{args.per_task_timeout:g}s)"
                        ),
                        "steps_used": 0,
                        "final_answer": "",
                    }
                )
                print(f"  [{i}/{total}] {task.task_id}: timeout", file=sys.stderr)
            else:
                graded = adapter.grade(
                    task, result, fhir_api_base=args.fhir_api_base
                )
                records.append(
                    {
                        "task_id": task.task_id,
                        "category": task.category,
                        "status": result.status,
                        "grade": graded.outcome,
                        "grade_detail": graded.detail,
                        "steps_used": result.steps_used,
                        "final_answer": result.final_answer,
                    }
                )
                print(
                    f"  [{i}/{total}] {task.task_id}: {graded.outcome}",
                    file=sys.stderr,
                )

            checkpoint()  # persist after every task so nothing is ever lost
    except KeyboardInterrupt:
        print("\n  interrupted — saving partial results", file=sys.stderr)

    checkpoint()
    summary = _summarize(total, records)
    print(
        f"MedAgentBench: {summary['passed']} pass / {summary['failed']} fail "
        f"/ {summary['ungraded']} ungraded (of {total}) -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
