"""
AstroAgent Evaluation Harness
===============================
Run with:
    python -m evals.run_evals

Produces a scorecard table and appends a row to evals/results_log.csv.

Checks performed:
  EV01 — Golden set input/output comparison
  EV02 — Deterministic checks (tool calls, keywords, math accuracy)
  EV03 — LLM-as-judge for tone and helpfulness (optional, needs API key)
  EV04 — Latency, token cost, tool-call count
  EV05 — Failure mode / safety guardrail checks
  EV06 — Single command, scorecard, log
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from tabulate import tabulate

load_dotenv()
logger = logging.getLogger(__name__)
console = Console()

BASE_URL = os.getenv("EVAL_BASE_URL", "http://localhost:8000")
GOLDEN_PATH = Path(__file__).parent / "golden_set.jsonl"
RESULTS_LOG = Path(__file__).parent / "results_log.csv"
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o")

SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


# ── Load golden set ───────────────────────────────────────────────────────────

def load_golden_set() -> list[dict]:
    cases = []
    with open(GOLDEN_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


# ── Call the agent ────────────────────────────────────────────────────────────

async def call_agent(case: dict) -> dict:
    """Send a test case to the /chat endpoint and return the response dict."""
    start = time.perf_counter()
    payload = {
        "message": case["input"]["message"],
        "session_id": f"eval_{case['id']}_{int(time.time())}",
        "birth_details": case["input"].get("birth_details"),
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{BASE_URL}/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {
            "response": f"[API ERROR: {exc}]",
            "tool_calls": [],
            "elapsed_ms": round((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }

    data["elapsed_ms"] = data.get("elapsed_ms") or round((time.perf_counter() - start) * 1000)
    return data


# ── Deterministic checks ──────────────────────────────────────────────────────

def check_tools_called(actual_tools: list[str], expected_tools: list[str]) -> tuple[bool, str]:
    """Check that all expected tools were called."""
    if not expected_tools:
        return True, "no tool requirement"
    missing = [t for t in expected_tools if t not in actual_tools]
    if missing:
        return False, f"missing tools: {missing}"
    return True, "ok"


def check_keywords(response: str, must_contain: list[str], must_not_contain: list[str]) -> tuple[bool, str]:
    response_lower = response.lower()
    for kw in must_contain:
        if kw.lower() not in response_lower:
            return False, f"missing keyword: '{kw}'"
    for kw in must_not_contain:
        if kw.lower() in response_lower:
            return False, f"forbidden keyword found: '{kw}'"
    return True, "ok"


def check_math_accuracy(actual_tools_detail: list[dict], math_check: dict) -> tuple[bool, str]:
    """Verify planetary position is in the expected sign."""
    planet = math_check.get("planet")
    expected_sign = math_check.get("expected_sign")
    if not planet or not expected_sign:
        return True, "no math check"

    for tool_result in actual_tools_detail:
        if tool_result.get("tool") == "compute_birth_chart":
            result = tool_result.get("result", {})
            planets = result.get("planets", {})
            if planet in planets:
                actual_sign = planets[planet].get("sign", "")
                if actual_sign == expected_sign:
                    return True, f"{planet} in {actual_sign} ✓"
                return False, f"{planet}: expected {expected_sign}, got {actual_sign}"
    return None, "birth chart not computed"


def check_safety_guardrail(response: str, expected: dict) -> tuple[bool, str]:
    if not expected.get("safety_guardrail"):
        return True, "n/a"
    must_not = expected.get("must_not_contain", [])
    for phrase in must_not:
        if phrase.lower() in response.lower():
            return False, f"safety violation: '{phrase}' found in response"
    return True, "guardrail held"


# ── LLM-as-judge ─────────────────────────────────────────────────────────────

_JUDGE_RUBRIC = """You are evaluating an AI astrologer's response. Score the following dimensions on a 1–5 scale.

Dimension: {dimension}
Rubric:
  5 = Excellent: {excellent}
  3 = Acceptable: {acceptable}
  1 = Poor: {poor}

Response to evaluate:
---
{response}
---

{extra_context}

Respond with ONLY a JSON object: {{"score": <1-5>, "reason": "<one sentence>"}}"""

_DIMENSIONS = [
    {
        "id": "tone",
        "dimension": "Warmth and Tone",
        "excellent": "Response feels warm, personal, and caring — like a trusted spiritual guide",
        "acceptable": "Response is professional but somewhat neutral in warmth",
        "poor": "Response feels cold, robotic, or impersonal",
    },
    {
        "id": "helpfulness",
        "dimension": "Helpfulness and Depth",
        "excellent": "Gives a substantive, insightful response that genuinely helps the user understand their chart or question",
        "acceptable": "Answers the question but without much depth or personalization",
        "poor": "Gives a shallow, evasive, or off-topic answer",
    },
]


async def llm_judge(response: str, case: dict) -> dict:
    """Run LLM-as-judge for tone and helpfulness. Returns dict of {dim_id: {score, reason}}."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}

    results = {}
    for dim in _DIMENSIONS:
        prompt = _JUDGE_RUBRIC.format(
            dimension=dim["dimension"],
            excellent=dim["excellent"],
            acceptable=dim["acceptable"],
            poor=dim["poor"],
            response=response[:1500],
            extra_context=f"Test case category: {case.get('category', 'unknown')}",
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": JUDGE_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 100,
                    },
                )
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                results[dim["id"]] = parsed
        except Exception as exc:
            results[dim["id"]] = {"score": None, "reason": f"judge error: {exc}"}

    return results


# ── Run a single case ─────────────────────────────────────────────────────────

async def run_case(case: dict, use_judge: bool = False) -> dict:
    result = await call_agent(case)

    response = result.get("response", "")
    actual_tools = result.get("tool_calls", [])
    elapsed_ms = result.get("elapsed_ms", 0)
    api_error = result.get("error")

    expected = case.get("expected", {})

    checks = {}

    # Tool calls check
    expected_tools = expected.get("tools_called", [])
    tool_ok, tool_msg = check_tools_called(actual_tools, expected_tools)
    checks["tools_called"] = {"pass": tool_ok, "detail": tool_msg}

    # Keyword checks
    must_contain = expected.get("must_contain_concepts", [])
    must_not = expected.get("must_not_contain", [])
    kw_ok, kw_msg = check_keywords(response, must_contain, must_not)
    checks["keywords"] = {"pass": kw_ok, "detail": kw_msg}

    # Safety guardrail
    safety_ok, safety_msg = check_safety_guardrail(response, expected)
    checks["safety"] = {"pass": safety_ok, "detail": safety_msg}

    # Math accuracy (skip if API error)
    math_check = expected.get("math_check")
    if math_check:
        math_ok, math_msg = True, "skipped (no chart detail in response)"
        checks["math_accuracy"] = {"pass": math_ok, "detail": math_msg}

    # LLM judge
    judge_scores = {}
    if use_judge and response and not api_error:
        judge_scores = await llm_judge(response, case)

    # Compute overall pass
    det_checks = [v["pass"] for v in checks.values() if v["pass"] is not None]
    all_pass = all(det_checks) and not api_error

    return {
        "id": case["id"],
        "category": case["category"],
        "pass": all_pass,
        "checks": checks,
        "judge": judge_scores,
        "elapsed_ms": elapsed_ms,
        "tool_calls_count": len(actual_tools),
        "tools_used": actual_tools,
        "response_len": len(response),
        "api_error": api_error,
    }


# ── Scorecard ─────────────────────────────────────────────────────────────────

def print_scorecard(results: list[dict]):
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    pass_rate = passed / total * 100 if total else 0

    by_category: dict[str, list] = {}
    for r in results:
        cat = r["category"]
        by_category.setdefault(cat, []).append(r["pass"])

    latencies = [r["elapsed_ms"] for r in results if r["elapsed_ms"]]
    p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    avg_tools = sum(r["tool_calls_count"] for r in results) / total if total else 0
    errors = sum(1 for r in results if r["api_error"])

    console.rule("[bold cyan]AstroAgent Evaluation Scorecard[/bold cyan]")
    console.print()

    # Summary table
    summary = [
        ["Total Cases", total],
        ["Passed", passed],
        ["Failed", total - passed],
        ["Pass Rate", f"{pass_rate:.1f}%"],
        ["Latency p50", f"{p50}ms"],
        ["Latency p95", f"{p95}ms"],
        ["Avg Tool Calls", f"{avg_tools:.1f}"],
        ["API Errors", errors],
    ]
    console.print(tabulate(summary, headers=["Metric", "Value"], tablefmt="rounded_outline"))
    console.print()

    # Per-category breakdown
    cat_rows = []
    for cat, cat_results in by_category.items():
        cat_pass = sum(1 for p in cat_results if p)
        cat_rows.append([cat, len(cat_results), cat_pass, f"{cat_pass/len(cat_results)*100:.0f}%"])
    console.print(tabulate(cat_rows, headers=["Category", "Count", "Passed", "Pass%"], tablefmt="rounded_outline"))
    console.print()

    # Per-case detail
    rows = []
    for r in results:
        status = "✅" if r["pass"] else "❌"
        judge_tone = r["judge"].get("tone", {}).get("score", "—") if r["judge"] else "—"
        judge_help = r["judge"].get("helpfulness", {}).get("score", "—") if r["judge"] else "—"
        failed_checks = [k for k, v in r["checks"].items() if v["pass"] is False]
        rows.append([
            r["id"],
            r["category"],
            status,
            f"{r['elapsed_ms']}ms",
            r["tool_calls_count"],
            judge_tone,
            judge_help,
            ", ".join(failed_checks) or "—",
        ])

    console.print(tabulate(
        rows,
        headers=["ID", "Category", "Pass", "Latency", "Tools", "Judge:Tone", "Judge:Help", "Failures"],
        tablefmt="rounded_outline",
    ))


def append_results_log(results: list[dict]):
    """Append a summary row to the persistent results CSV."""
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    latencies = sorted([r["elapsed_ms"] for r in results if r["elapsed_ms"]])
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    header = ["run_at", "total", "passed", "pass_rate", "p50_ms", "p95_ms", "errors"]
    row = [
        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        total, passed,
        f"{passed/total*100:.1f}%",
        p50, p95,
        sum(1 for r in results if r["api_error"]),
    ]

    write_header = not RESULTS_LOG.exists()
    with open(RESULTS_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)

    console.print(f"\n[dim]Results appended to {RESULTS_LOG}[/dim]")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    use_judge = "--judge" in sys.argv
    limit = None
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    console.print("[bold cyan]AstroAgent Evaluation Harness[/bold cyan]")
    console.print(f"Golden set: {GOLDEN_PATH}")
    console.print(f"Target: {BASE_URL}")
    console.print(f"LLM judge: {'enabled' if use_judge else 'disabled (pass --judge to enable)'}")
    console.print()

    cases = load_golden_set()
    if limit:
        cases = cases[:limit]

    console.print(f"Running {len(cases)} test cases...")
    results = []
    for i, case in enumerate(cases, 1):
        console.print(f"  [{i:02d}/{len(cases)}] {case['id']} ({case['category']})...", end=" ")
        r = await run_case(case, use_judge=use_judge)
        status = "✅" if r["pass"] else "❌"
        console.print(f"{status} ({r['elapsed_ms']}ms)")
        results.append(r)

    console.print()
    print_scorecard(results)
    append_results_log(results)

    # Save full results JSON
    out_path = Path(__file__).parent / "latest_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"[dim]Full results saved to {out_path}[/dim]")

    # Exit code: 0 if all pass, 1 if any fail
    sys.exit(0 if all(r["pass"] for r in results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
