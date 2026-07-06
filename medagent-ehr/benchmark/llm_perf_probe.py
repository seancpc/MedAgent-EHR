"""Measure serving metrics of the local llama-server (OpenAI-compatible /v1).

Reports TTFT (time to first token), generation throughput (tokens/s), total
latency, and GPU VRAM usage — the numbers for the portfolio "performance &
cost" table. Runs against a live llama-server; no other services needed.

Usage (desktop, with llama-server running):
    python medagent-ehr/benchmark/llm_perf_probe.py --base-url http://localhost:11435
    python medagent-ehr/benchmark/llm_perf_probe.py --runs 5 --concurrency 4

--base-url / --model default to OLLAMA_BASE_URL / OLLAMA_MODEL from the
environment (or medagent-ehr/.env values exported by hand).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time

import httpx

DEFAULT_PROMPT = (
    "List 25 common clinical laboratory tests. For each, give its name and a "
    "one-sentence description of what it measures."
)


def _normalize_base(url: str) -> str:
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _one_run(base: str, model: str, prompt: str, max_tokens: int) -> dict:
    """One streaming chat completion; returns timing metrics."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t_start = time.monotonic()
    t_first = None
    t_last = None
    chunk_tokens = 0
    usage_tokens = None
    sample_chunk = ""

    with httpx.Client(timeout=600) as client:
        with client.stream("POST", f"{base}/chat/completions", json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload.strip() == "[DONE]":
                    break
                if not sample_chunk:
                    sample_chunk = payload[:400]
                chunk = json.loads(payload)
                usage = chunk.get("usage")
                if usage and usage.get("completion_tokens"):
                    usage_tokens = usage["completion_tokens"]
                choices = chunk.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                # count reasoning tokens too — models with thinking enabled
                # (e.g. Gemma) stream them as delta.reasoning_content, and the
                # generation rate is the same metric either way
                if delta.get("content") or delta.get("reasoning_content"):
                    now = time.monotonic()
                    if t_first is None:
                        t_first = now
                    t_last = now
                    chunk_tokens += 1

    t_end = time.monotonic()
    if t_first is None:  # nothing token-like came back at all
        raise RuntimeError(
            "stream returned no content/reasoning deltas — first raw chunk was: "
            f"{sample_chunk or '(no data lines at all)'}"
        )
    tokens = usage_tokens if usage_tokens else chunk_tokens
    gen_time = (t_last - t_first) if t_last and t_last > t_first else 0.0
    return {
        "ttft_s": t_first - t_start,
        "total_s": t_end - t_start,
        "tokens": tokens,
        "gen_tok_per_s": (tokens - 1) / gen_time if gen_time > 0 else 0.0,
        "tokens_exact": usage_tokens is not None,
    }


def _vram() -> str:
    """GPU memory used/total via nvidia-smi, or 'n/a' if unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()[0]
        used, total = (int(x) for x in out.split(","))
        return f"{used / 1024:.1f} / {total / 1024:.1f} GB"
    except Exception:
        return "n/a"


def _concurrency_run(
    base: str, model: str, prompt: str, max_tokens: int, workers: int
) -> dict:
    """`workers` simultaneous requests; returns aggregate throughput."""
    results: list[dict] = []
    errors: list[str] = []
    lock = threading.Lock()

    def work() -> None:
        try:
            r = _one_run(base, model, prompt, max_tokens)
            with lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001 - collect, don't crash the probe
            with lock:
                errors.append(str(exc))

    t0 = time.monotonic()
    threads = [threading.Thread(target=work) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - t0
    total_tokens = sum(r["tokens"] for r in results)
    return {
        "workers": workers,
        "ok": len(results),
        "errors": errors,
        "wall_s": wall,
        "aggregate_tok_per_s": total_tokens / wall if wall > 0 else 0.0,
    }


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="LLM serving performance probe")
    parser.add_argument("--base-url", default=os.environ.get("OLLAMA_BASE_URL", ""))
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "default"))
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--runs", type=int, default=5,
                        help="sequential runs for the latency stats (default 5)")
    parser.add_argument("--concurrency", type=int, default=0,
                        help="if >0, also run one batch of N simultaneous requests")
    parser.add_argument("--out", default="",
                        help="optional path to save raw results as JSON")
    args = parser.parse_args()

    if not args.base_url:
        print("error: --base-url or OLLAMA_BASE_URL is required", file=sys.stderr)
        return 2
    base = _normalize_base(args.base_url)

    print(f"probe: {base}  model={args.model}  max_tokens={args.max_tokens}")
    print("warmup run ...")
    _one_run(base, args.model, args.prompt, args.max_tokens)  # exclude from stats

    runs = []
    for i in range(1, args.runs + 1):
        r = _one_run(base, args.model, args.prompt, args.max_tokens)
        runs.append(r)
        exact = "" if r["tokens_exact"] else " (token count approximated by chunks)"
        print(
            f"  run {i}/{args.runs}: TTFT {r['ttft_s']:.3f}s | "
            f"{r['gen_tok_per_s']:.1f} tok/s | total {r['total_s']:.2f}s | "
            f"{r['tokens']} tokens{exact}"
        )

    conc = None
    if args.concurrency > 0:
        print(f"concurrency batch: {args.concurrency} simultaneous requests ...")
        conc = _concurrency_run(
            base, args.model, args.prompt, args.max_tokens, args.concurrency
        )

    ttfts = [r["ttft_s"] for r in runs]
    rates = [r["gen_tok_per_s"] for r in runs]
    totals = [r["total_s"] for r in runs]
    vram = _vram()

    print("\n--- paste-ready markdown ---\n")
    print("| Metric | Value |")
    print("|---|---|")
    print(f"| TTFT (median / mean) | {statistics.median(ttfts):.3f}s / "
          f"{statistics.mean(ttfts):.3f}s |")
    print(f"| Generation throughput (median) | "
          f"{statistics.median(rates):.1f} tokens/s |")
    print(f"| Latency, {args.max_tokens}-token response (median) | "
          f"{statistics.median(totals):.2f}s |")
    if conc:
        print(f"| Aggregate throughput @ {conc['workers']} concurrent | "
              f"{conc['aggregate_tok_per_s']:.1f} tokens/s "
              f"({conc['ok']}/{conc['workers']} ok) |")
    print(f"| GPU VRAM (used / total) | {vram} |")

    if args.out:
        payload = {"base_url": base, "model": args.model,
                   "max_tokens": args.max_tokens, "runs": runs,
                   "concurrency": conc, "vram": vram}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"\nraw results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
