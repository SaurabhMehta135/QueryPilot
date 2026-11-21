"""
evals/runner.py - Execution accuracy evaluation runner for QueryPilot Phase 8.
Evaluates accuracy across dataset splits (dev, held-out test, or full accuracy set).
Enforces database freeze, LLM prompt-hash caching, request throttling, and interrupt policy.
Supports both strict (exact columns/rows) and lenient (contains reference columns, same rows) scoring.
Computes 95% Wilson confidence intervals.
"""

import os
import sys
import json
import time
import math
import sqlite3
import hashlib
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.config import settings
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.mcp_client.client import DirectMCPClient
from evals.cached_provider import CachedLLMProvider

FROZEN_DB_SHA256 = "2546fe654e375e3721c9e3593f0baf357649866eedaae0dc1b63149ee6f08961"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample.db")
EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(EVALS_DIR, "results")
RUN4_DIR = os.path.join(RESULTS_DIR, "run_4")
os.makedirs(RUN4_DIR, exist_ok=True)


def verify_database_freeze() -> str:
    """Verifies that the database has not been modified and matches frozen SHA-256 hash."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    with open(DB_PATH, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    if current_hash != FROZEN_DB_SHA256:
        raise RuntimeError(
            f"Database integrity verification FAILED!\n"
            f"Expected frozen hash: {FROZEN_DB_SHA256}\n"
            f"Actual database hash: {current_hash}\n"
            f"Evaluations require an immutable frozen database."
        )
    return current_hash


def normalize_val(val: Any) -> Any:
    """Normalizes scalar value for comparison: rounds floats to 2 decimals, normalizes numeric strings."""
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, 2)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            f = float(val)
            if not math.isnan(f) and not math.isinf(f):
                return round(f, 2)
        except (ValueError, TypeError):
            pass
        return val.strip()
    return str(val)


def normalize_row(row: Tuple[Any, ...]) -> Tuple[Any, ...]:
    return tuple(normalize_val(v) for v in row)


def compare_results_strict(gen_rows: List[Tuple], ref_rows: List[Tuple], order_matters: bool = False) -> bool:
    """
    Strict execution match:
    1. Exact same number of columns.
    2. Exact same number of rows.
    3. Column-order-insensitive: any permutation of generated columns matches reference rows.
    4. Numeric tolerance: float rounding to 2 decimal places.
    5. Order-sensitive if order_matters=True, else multiset equality (Counter).
    """
    if len(gen_rows) != len(ref_rows):
        return False
    if not gen_rows and not ref_rows:
        return True
    if len(gen_rows[0]) != len(ref_rows[0]):
        return False

    k = len(ref_rows[0])
    norm_ref = [normalize_row(r) for r in ref_rows]
    norm_gen = [normalize_row(r) for r in gen_rows]

    # Fast path 1: Identity permutation
    if order_matters:
        if norm_gen == norm_ref:
            return True
    else:
        if Counter(norm_gen) == Counter(norm_ref):
            return True

    # Fast path 2: Any column permutation
    import itertools
    for perm in itertools.permutations(range(k)):
        if perm == tuple(range(k)):
            continue
        proj_gen = [tuple(r[i] for i in perm) for r in norm_gen]
        if order_matters:
            if proj_gen == norm_ref:
                return True
        else:
            if Counter(proj_gen) == Counter(norm_ref):
                return True

    return False


# Alias for backwards compatibility
compare_results = compare_results_strict


def compare_results_lenient(
    gen_rows: List[Tuple],
    ref_rows: List[Tuple],
    order_matters: bool = False,
    gen_cols: Optional[List[str]] = None,
    ref_cols: Optional[List[str]] = None,
) -> bool:
    """
    Lenient execution match:
    1. Generated query has >= number of columns in reference.
    2. Exact same number of rows.
    3. Column-order-insensitive & projection subset: any permutation of size k of generated columns matches reference.
    4. Numeric tolerance: float rounding to 2 decimal places.
    5. Order-sensitive if order_matters=True, else multiset equality (Counter).
    """
    if compare_results_strict(gen_rows, ref_rows, order_matters=order_matters):
        return True

    if len(gen_rows) != len(ref_rows) or not ref_rows or not gen_rows:
        return False

    n_ref = len(ref_rows[0])
    n_gen = len(gen_rows[0])
    if n_gen < n_ref:
        return False

    norm_ref = [normalize_row(r) for r in ref_rows]
    norm_gen = [normalize_row(r) for r in gen_rows]

    import itertools
    for col_indices in itertools.permutations(range(n_gen), n_ref):
        proj_gen = [tuple(r[i] for i in col_indices) for r in norm_gen]
        if order_matters:
            if proj_gen == norm_ref:
                return True
        else:
            if Counter(proj_gen) == Counter(norm_ref):
                return True

    return False


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Computes Wilson score 95% confidence interval [lower, upper] as percentages (0-100)."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.95996  # 95% confidence
    p = successes / total
    denominator = 1 + z**2 / total
    centre_adjusted_probability = p + z**2 / (2 * total)
    adjusted_sd = math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    lower = (centre_adjusted_probability - z * adjusted_sd) / denominator
    upper = (centre_adjusted_probability + z * adjusted_sd) / denominator
    return (round(max(0.0, lower) * 100, 1), round(min(1.0, upper) * 100, 1))


async def run_accuracy_evaluation(
    dataset_name: str = "test.jsonl",
    provider_name: str = "gemini",
    throttle_seconds: float = 0.5,
    max_questions: Optional[int] = None,
    skip_explainer: bool = True,
) -> Dict[str, Any]:
    """Runs execution accuracy evaluation on the specified dataset split."""
    db_hash = verify_database_freeze()
    print(f"=== Starting Accuracy Evaluation ({dataset_name}) ===")
    print(f"Database verified frozen: {db_hash}")

    dataset_path = os.path.join(EVALS_DIR, "datasets", dataset_name)
    with open(dataset_path, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    if max_questions:
        questions = questions[:max_questions]

    print(f"Loaded {len(questions)} evaluation questions from {dataset_name}.")

    # Set up LLM client with caching decorator and Groq fallback disabled
    raw_llm = LLMClient(provider=provider_name, allow_fallback=False)
    cached_llm_provider = CachedLLMProvider(
        inner_provider=raw_llm.provider,
        throttle_seconds=throttle_seconds,
    )
    llm_client = LLMClient(custom_provider=cached_llm_provider, allow_fallback=False)

    mcp_client = DirectMCPClient()
    checkpointer = MemorySaver()
    app = create_querypilot_graph(
        llm_client=llm_client,
        mcp_client=mcp_client,
        checkpointer=checkpointer,
    ).compile(checkpointer=checkpointer)

    # Unmasked read-only connection for metric calculation
    ro_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro_cur = ro_conn.cursor()

    eval_results = []
    strict_correct_count = 0
    lenient_correct_count = 0
    clarification_count = 0
    blocked_count = 0
    failed_count = 0

    diff_stats = {
        "easy": {"total": 0, "strict_correct": 0, "lenient_correct": 0},
        "medium": {"total": 0, "strict_correct": 0, "lenient_correct": 0},
        "hard": {"total": 0, "strict_correct": 0, "lenient_correct": 0},
    }

    start_eval_time = time.time()

    for idx, q in enumerate(questions):
        qid = q["id"]
        question_text = q["question"]
        ref_sql = q["reference_sql"]
        diff = q.get("difficulty", "medium")
        order_matters = q.get("order_matters", False)

        diff_stats[diff]["total"] += 1

        # Execute reference SQL
        ro_cur.execute(ref_sql)
        ref_rows = ro_cur.fetchall()
        ref_cols = [d[0] for d in ro_cur.description] if ro_cur.description else []

        # Run query through QueryPilot graph
        thread_id = f"eval-{qid}"
        state: GraphState = {
            "question": question_text,
            "retry_count": 0,
            "trace": [],
            "final_status": "in_progress",
            "skip_explainer": skip_explainer,
        }

        q_start = time.perf_counter()
        final_state = await app.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
        q_duration = (time.perf_counter() - q_start) * 1000

        # Handle interrupts: approval or clarification
        status = final_state.get("final_status")

        # Check for interrupt state
        snapshot = app.get_state(config={"configurable": {"thread_id": thread_id}})
        if snapshot.next and len(snapshot.next) > 0:
            next_node = snapshot.next[0]
            if next_node == "approval_node":
                # Policy: Auto-approve expensive queries during evaluation
                resume_cmd = Command(resume=True)
                final_state = await app.ainvoke(resume_cmd, config={"configurable": {"thread_id": thread_id}})
                status = final_state.get("final_status", status)
            elif next_node == "clarification_node":
                # Policy: Record clarification requested, not a failure
                status = "clarification_requested"

        generated_sql = final_state.get("sql")
        is_strict = False
        is_lenient = False
        gen_rows = []
        gen_cols = []
        error_msg = None

        if status == "clarification_requested":
            clarification_count += 1
        elif status == "blocked":
            blocked_count += 1
        elif generated_sql:
            try:
                ro_cur.execute(generated_sql)
                gen_rows = ro_cur.fetchall()
                gen_cols = [d[0] for d in ro_cur.description] if ro_cur.description else []
                is_strict = compare_results_strict(gen_rows, ref_rows, order_matters=order_matters)
                is_lenient = compare_results_lenient(gen_rows, ref_rows, gen_cols=gen_cols, ref_cols=ref_cols, order_matters=order_matters)
                if is_strict:
                    strict_correct_count += 1
                    diff_stats[diff]["strict_correct"] += 1
                if is_lenient:
                    lenient_correct_count += 1
                    diff_stats[diff]["lenient_correct"] += 1
                if not is_strict:
                    failed_count += 1
            except Exception as e:
                error_msg = str(e)
                failed_count += 1
        else:
            failed_count += 1

        # Record step stats from trace
        trace = final_state.get("trace", [])
        retries = final_state.get("retry_count", 0)

        eval_results.append({
            "id": qid,
            "difficulty": diff,
            "question": question_text,
            "reference_sql": ref_sql,
            "generated_sql": generated_sql,
            "final_status": status,
            "is_correct_strict": is_strict,
            "is_correct_lenient": is_lenient,
            "is_correct": is_strict,
            "ref_row_count": len(ref_rows),
            "gen_row_count": len(gen_rows),
            "retries": retries,
            "latency_ms": round(q_duration, 2),
            "error": error_msg,
        })

        outcome_symbol = "✓" if is_strict else ("~" if is_lenient else ("?" if status == "clarification_requested" else "✗"))
        print(f"[{idx+1}/{len(questions)}] {outcome_symbol} {qid} ({diff}): strict={is_strict}, lenient={is_lenient}, status={status}")

    total_duration = time.time() - start_eval_time
    total_q = len(questions)
    strict_acc = round(strict_correct_count / total_q, 4) if total_q > 0 else 0.0
    lenient_acc = round(lenient_correct_count / total_q, 4) if total_q > 0 else 0.0
    strict_ci = wilson_score_interval(strict_correct_count, total_q)
    lenient_ci = wilson_score_interval(lenient_correct_count, total_q)

    # Operational metrics computed ONLY from uncached calls
    uncached_count = len(cached_llm_provider.uncached_model_latency_ms)
    avg_uncached_latency_ms = round(sum(cached_llm_provider.uncached_model_latency_ms) / uncached_count, 1) if uncached_count > 0 else None
    avg_uncached_wait_ms = round(sum(cached_llm_provider.uncached_retry_wait_ms) / uncached_count, 1) if uncached_count > 0 else None
    avg_uncached_tokens = round(sum(cached_llm_provider.uncached_total_tokens) / uncached_count, 1) if uncached_count > 0 else None
    avg_uncached_prompt_tokens = round(sum(cached_llm_provider.uncached_prompt_tokens) / uncached_count, 1) if uncached_count > 0 else None
    avg_uncached_completion_tokens = round(sum(cached_llm_provider.uncached_completion_tokens) / uncached_count, 1) if uncached_count > 0 else None

    p95_uncached_latency_ms = None
    if uncached_count > 0:
        sorted_latencies = sorted(cached_llm_provider.uncached_model_latency_ms)
        p95_idx = int(0.95 * uncached_count)
        p95_uncached_latency_ms = round(sorted_latencies[min(p95_idx, uncached_count - 1)], 1)

    summary = {
        "dataset": dataset_name,
        "database_sha256": db_hash,
        "provider": provider_name,
        "groq_fallback_disabled": True,
        "skip_explainer": skip_explainer,
        "total_questions": total_q,
        "strict_execution_accuracy": strict_acc,
        "strict_correct_count": strict_correct_count,
        "strict_wilson_ci_95": strict_ci,
        "lenient_execution_accuracy": lenient_acc,
        "lenient_correct_count": lenient_correct_count,
        "lenient_wilson_ci_95": lenient_ci,
        "overall_execution_accuracy": strict_acc,
        "correct_count": strict_correct_count,
        "status_distribution": {
            "success": strict_correct_count,
            "clarification_requested": clarification_count,
            "blocked": blocked_count,
            "failed": failed_count,
        },
        "accuracy_by_difficulty": {
            d: {
                "total": s["total"],
                "strict_correct": s["strict_correct"],
                "strict_accuracy": round(s["strict_correct"] / s["total"], 4) if s["total"] > 0 else 0.0,
                "strict_wilson_ci_95": wilson_score_interval(s["strict_correct"], s["total"]),
                "lenient_correct": s["lenient_correct"],
                "lenient_accuracy": round(s["lenient_correct"] / s["total"], 4) if s["total"] > 0 else 0.0,
                "lenient_wilson_ci_95": wilson_score_interval(s["lenient_correct"], s["total"]),
                "correct": s["strict_correct"],
                "accuracy": round(s["strict_correct"] / s["total"], 4) if s["total"] > 0 else 0.0,
            }
            for d, s in diff_stats.items()
        },
        "cache_stats": {
            "hits": cached_llm_provider.cache_hits,
            "misses": cached_llm_provider.cache_misses,
            "hit_rate": round(cached_llm_provider.cache_hits / max(1, cached_llm_provider.cache_hits + cached_llm_provider.cache_misses), 4),
        },
        "uncached_operational_metrics": {
            "uncached_call_count": uncached_count,
            "avg_model_latency_ms": avg_uncached_latency_ms,
            "p95_model_latency_ms": p95_uncached_latency_ms,
            "avg_retry_wait_ms": avg_uncached_wait_ms,
            "avg_tokens_per_call": avg_uncached_tokens,
            "avg_prompt_tokens_per_call": avg_uncached_prompt_tokens,
            "avg_completion_tokens_per_call": avg_uncached_completion_tokens,
        },
        "total_eval_duration_seconds": round(total_duration, 2),
        "details": eval_results,
    }

    out_file = os.path.join(RUN4_DIR, f"accuracy_{dataset_name.replace('.jsonl', '')}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Evaluation Complete ({dataset_name}) ===")
    print(f"Strict Accuracy:  {strict_acc * 100:.1f}% ({strict_correct_count}/{total_q}) [95% CI: {strict_ci[0]}% - {strict_ci[1]}%]")
    print(f"Lenient Accuracy: {lenient_acc * 100:.1f}% ({lenient_correct_count}/{total_q}) [95% CI: {lenient_ci[0]}% - {lenient_ci[1]}%]")
    for d, s in summary["accuracy_by_difficulty"].items():
        print(f"  {d.capitalize()}: Strict={s['strict_accuracy'] * 100:.1f}% ({s['strict_correct']}/{s['total']}), Lenient={s['lenient_accuracy'] * 100:.1f}% ({s['lenient_correct']}/{s['total']})")
    print(f"Saved results to {out_file}")

    return summary


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl"
    provider = sys.argv[2] if len(sys.argv) > 2 else "gemini"
    asyncio.run(run_accuracy_evaluation(dataset_name=split, provider_name=provider))
