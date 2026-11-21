"""
evals/ablation.py - Ablation study runner comparing four system configurations:
- Config A: Single-shot baseline (full schema in prompt, one SQL generation, no validator, no retry)
- Config B: Config A + Dynamic schema linking (Schema Agent)
- Config C: Config B + AST Validator & Limit Injection
- Config D: Full QueryPilot (Config C + Self-Correction Loop)

Reports execution accuracy, Wilson 95% CIs, uncached/cached latency, tokens, retries,
paired win/loss counts, and raw per-question JSON records for every configuration.
"""

import os
import sys
import json
import time
import sqlite3
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.mcp_client.client import DirectMCPClient
from app.guardrails.sql_validator import SQLValidator
from evals.cached_provider import CachedLLMProvider
from evals.runner import compare_results, compare_results_strict, compare_results_lenient, verify_database_freeze, wilson_score_interval

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample.db")
EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(EVALS_DIR, "results")
RUN4_DIR = os.path.join(RESULTS_DIR, "run_4")
os.makedirs(RUN4_DIR, exist_ok=True)


async def run_ablation_study(
    dataset_name: str = "dev.jsonl",
    provider_name: str = "gemini",
    max_questions: int = 50,
) -> Dict[str, Any]:
    verify_database_freeze()
    print(f"=== Starting Ablation Study on {dataset_name} ({max_questions} questions) ===")

    dataset_path = os.path.join(EVALS_DIR, "datasets", dataset_name)
    with open(dataset_path, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()][:max_questions]

    raw_llm = LLMClient(provider=provider_name, allow_fallback=False)
    cached_llm = CachedLLMProvider(raw_llm.provider, max_tpm=7000, throttle_seconds=1.2)
    llm_client = LLMClient(custom_provider=cached_llm, allow_fallback=False)
    mcp_client = DirectMCPClient()
    validator = SQLValidator(known_tables={"categories", "products", "customers", "orders", "order_items", "payments", "reviews"})

    ro_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro_cur = ro_conn.cursor()

    from app.agents.sql_writer import SQLWriterAgent
    from app.agents.schema_agent import SchemaAgent
    from app.agents.prompt_loader import load_prompt
    from app.guardrails.injection import wrap_untrusted_data

    # Standard writer prompt used across baseline and full system
    writer_prompt_text = load_prompt("sql_writer.md")

    configs = [
        "Config A: Single-shot Baseline",
        "Config B: Config A + Schema Linking",
        "Config C: Config B + AST Validator & Limit Injection",
        "Config D: Full QueryPilot (Self-Correction)",
    ]

    ablation_stats = {
        cfg: {
            "strict_correct": 0,
            "lenient_correct": 0,
            "total": len(questions),
            "total_latency_ms": 0.0,
            "total_tokens": 0,
            "total_retries": 0,
            "details": [],
        }
        for cfg in configs
    }

    # Full QueryPilot graph for Config D
    full_graph = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client).compile()

    # Pre-fetch complete database schema overview for Config A
    all_tables = await mcp_client.list_tables()
    full_schema_ctx = {}
    for t in all_tables:
        full_schema_ctx[t] = await mcp_client.describe_table(t)

    # Per question comparison tracker
    per_question_outcomes_strict = []
    per_question_outcomes_lenient = []

    # Checkpoint loading for resumable evaluation
    checkpoint_file = os.path.join(RUN4_DIR, "ablation_checkpoint.json")
    completed_qids = set()
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
            ablation_stats = ckpt.get("ablation_stats", ablation_stats)
            per_question_outcomes_strict = ckpt.get("per_question_outcomes_strict", [])
            per_question_outcomes_lenient = ckpt.get("per_question_outcomes_lenient", [])
            completed_qids = {r["id"] for r in per_question_outcomes_strict}
            print(f"Resuming ablation study from checkpoint: {len(completed_qids)}/{len(questions)} already completed.")
        except Exception as e:
            print(f"Warning: could not read checkpoint: {e}")

    for idx, q in enumerate(questions):
        qid = q["id"]
        if qid in completed_qids:
            continue
        q_text = q["question"]
        ref_sql = q["reference_sql"]
        order_matters = q.get("order_matters", False)

        ro_cur.execute(ref_sql)
        ref_rows = ro_cur.fetchall()
        ref_cols = [d[0] for d in ro_cur.description] if ro_cur.description else []

        # -------------------------------------------------------------
        # CONFIG A: Single-shot Baseline (Full schema, 1 LLM call, no validator)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        wrapped_full_schema = wrap_untrusted_data(full_schema_ctx, label="Full Database Schema Context")
        prompt_a = (
            f"User Question: {q_text}\n\n"
            f"{wrapped_full_schema}\n"
        )
        from app.agents.models import SQLProposal
        res_a = await llm_client.generate_structured(
            prompt=prompt_a,
            response_model=SQLProposal,
            system_instruction=writer_prompt_text,
        )
        dur_a = (time.perf_counter() - t0) * 1000
        sql_a_parsed = res_a.data.sql if res_a and res_a.data else ""

        strict_a = False
        lenient_a = False
        try:
            if sql_a_parsed:
                ro_cur.execute(sql_a_parsed)
                gen_rows_a = ro_cur.fetchall()
                strict_a = compare_results_strict(gen_rows_a, ref_rows, order_matters)
                lenient_a = compare_results_lenient(gen_rows_a, ref_rows, order_matters)
        except Exception:
            pass

        tok_a = res_a.total_tokens if res_a else 0
        cfg_a_name = configs[0]
        ablation_stats[cfg_a_name]["strict_correct"] += int(strict_a)
        ablation_stats[cfg_a_name]["lenient_correct"] += int(lenient_a)
        ablation_stats[cfg_a_name]["total_latency_ms"] += dur_a
        ablation_stats[cfg_a_name]["total_tokens"] += tok_a
        ablation_stats[cfg_a_name]["details"].append({
            "id": qid,
            "question": q_text,
            "generated_sql": sql_a_parsed,
            "strict_correct": strict_a,
            "lenient_correct": lenient_a,
            "tokens": tok_a,
            "latency_ms": round(dur_a, 2),
        })

        # -------------------------------------------------------------
        # CONFIG B: Config A + Schema Linking (Schema Agent)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        schema_agent = SchemaAgent(llm_client=llm_client, mcp_client=mcp_client)
        schema_b = await schema_agent.select_schema(q_text)

        writer = SQLWriterAgent(llm_client=llm_client)
        proposal_b = await writer.write_sql(q_text, schema_b.data.model_dump())
        dur_b = (time.perf_counter() - t0) * 1000

        sql_b = proposal_b.data.sql if proposal_b and proposal_b.data else ""
        strict_b = False
        lenient_b = False
        try:
            if sql_b:
                ro_cur.execute(sql_b)
                gen_rows_b = ro_cur.fetchall()
                strict_b = compare_results_strict(gen_rows_b, ref_rows, order_matters)
                lenient_b = compare_results_lenient(gen_rows_b, ref_rows, order_matters)
        except Exception:
            pass

        tok_b = (schema_b.total_tokens if schema_b else 0) + (proposal_b.total_tokens if proposal_b else 0)
        cfg_b_name = configs[1]
        ablation_stats[cfg_b_name]["strict_correct"] += int(strict_b)
        ablation_stats[cfg_b_name]["lenient_correct"] += int(lenient_b)
        ablation_stats[cfg_b_name]["total_latency_ms"] += dur_b
        ablation_stats[cfg_b_name]["total_tokens"] += tok_b
        ablation_stats[cfg_b_name]["details"].append({
            "id": qid,
            "question": q_text,
            "generated_sql": sql_b,
            "strict_correct": strict_b,
            "lenient_correct": lenient_b,
            "tokens": tok_b,
            "latency_ms": round(dur_b, 2),
        })

        # -------------------------------------------------------------
        # CONFIG C: Config B + AST Validator & Limit Injection
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        val_res_c = validator.validate_and_rewrite(sql_b)
        dur_c = dur_b + ((time.perf_counter() - t0) * 1000)

        strict_c = False
        lenient_c = False
        sql_c = val_res_c.rewritten_sql if val_res_c.is_safe else None
        if val_res_c.is_safe and sql_c:
            try:
                ro_cur.execute(sql_c)
                gen_rows_c = ro_cur.fetchall()
                strict_c = compare_results_strict(gen_rows_c, ref_rows, order_matters)
                lenient_c = compare_results_lenient(gen_rows_c, ref_rows, order_matters)
            except Exception:
                pass

        cfg_c_name = configs[2]
        ablation_stats[cfg_c_name]["strict_correct"] += int(strict_c)
        ablation_stats[cfg_c_name]["lenient_correct"] += int(lenient_c)
        ablation_stats[cfg_c_name]["total_latency_ms"] += dur_c
        ablation_stats[cfg_c_name]["total_tokens"] += tok_b
        ablation_stats[cfg_c_name]["details"].append({
            "id": qid,
            "question": q_text,
            "generated_sql": sql_c,
            "strict_correct": strict_c,
            "lenient_correct": lenient_c,
            "tokens": tok_b,
            "latency_ms": round(dur_c, 2),
        })

        # -------------------------------------------------------------
        # CONFIG D: Full QueryPilot (Config C + Self-Correction Loop)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        state_d: GraphState = {
            "question": q_text,
            "retry_count": 0,
            "trace": [],
            "skip_explainer": True,
        }
        res_d = await full_graph.ainvoke(state_d)
        dur_d = (time.perf_counter() - t0) * 1000

        sql_d = res_d.get("sql", "")
        strict_d = False
        lenient_d = False
        if sql_d:
            try:
                ro_cur.execute(sql_d)
                gen_rows_d = ro_cur.fetchall()
                strict_d = compare_results_strict(gen_rows_d, ref_rows, order_matters)
                lenient_d = compare_results_lenient(gen_rows_d, ref_rows, order_matters)
            except Exception:
                pass

        retries_d = res_d.get("retry_count", 0)
        tok_d = sum(s.get("prompt_tokens", 0) + s.get("completion_tokens", 0) for s in res_d.get("trace", []) if isinstance(s, dict))

        cfg_d_name = configs[3]
        ablation_stats[cfg_d_name]["strict_correct"] += int(strict_d)
        ablation_stats[cfg_d_name]["lenient_correct"] += int(lenient_d)
        ablation_stats[cfg_d_name]["total_latency_ms"] += dur_d
        ablation_stats[cfg_d_name]["total_tokens"] += tok_d
        ablation_stats[cfg_d_name]["total_retries"] += retries_d
        ablation_stats[cfg_d_name]["details"].append({
            "id": qid,
            "question": q_text,
            "generated_sql": sql_d,
            "strict_correct": strict_d,
            "lenient_correct": lenient_d,
            "tokens": tok_d,
            "retries": retries_d,
            "latency_ms": round(dur_d, 2),
        })

        per_question_outcomes_strict.append({
            "id": qid,
            "question": q_text,
            "Config A": strict_a,
            "Config B": strict_b,
            "Config C": strict_c,
            "Config D": strict_d,
        })
        per_question_outcomes_lenient.append({
            "id": qid,
            "question": q_text,
            "Config A": lenient_a,
            "Config B": lenient_b,
            "Config C": lenient_c,
            "Config D": lenient_d,
        })

        print(f"[{idx+1}/{len(questions)}] {qid}: A_strict={int(strict_a)} B_strict={int(strict_b)} C_strict={int(strict_c)} D_strict={int(strict_d)} | D_lenient={int(lenient_d)}")

        # Save resumable checkpoint
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump({
                "ablation_stats": ablation_stats,
                "per_question_outcomes_strict": per_question_outcomes_strict,
                "per_question_outcomes_lenient": per_question_outcomes_lenient,
            }, f, indent=2)

    # Compute paired win / loss counts
    def compute_paired(outcomes: list, c1: str, c2: str) -> Dict[str, int]:
        c1_wins = sum(1 for row in outcomes if row[c1] and not row[c2])
        c2_wins = sum(1 for row in outcomes if row[c2] and not row[c1])
        both_correct = sum(1 for row in outcomes if row[c1] and row[c2])
        both_wrong = sum(1 for row in outcomes if not row[c1] and not row[c2])
        return {
            f"{c1}_wins": c1_wins,
            f"{c2}_wins": c2_wins,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "ties": both_correct + both_wrong,
        }

    paired_comparisons_strict = {
        "D_vs_A": compute_paired(per_question_outcomes_strict, "Config D", "Config A"),
        "D_vs_B": compute_paired(per_question_outcomes_strict, "Config D", "Config B"),
        "D_vs_C": compute_paired(per_question_outcomes_strict, "Config D", "Config C"),
        "C_vs_B": compute_paired(per_question_outcomes_strict, "Config C", "Config B"),
        "B_vs_A": compute_paired(per_question_outcomes_strict, "Config B", "Config A"),
    }
    paired_comparisons_lenient = {
        "D_vs_A": compute_paired(per_question_outcomes_lenient, "Config D", "Config A"),
        "D_vs_B": compute_paired(per_question_outcomes_lenient, "Config D", "Config B"),
        "D_vs_C": compute_paired(per_question_outcomes_lenient, "Config D", "Config C"),
        "C_vs_B": compute_paired(per_question_outcomes_lenient, "Config C", "Config B"),
        "B_vs_A": compute_paired(per_question_outcomes_lenient, "Config B", "Config A"),
    }

    # Compute summary table
    summary_table = []
    n = len(questions)
    for cfg in configs:
        st = ablation_stats[cfg]
        strict_ci = wilson_score_interval(st["strict_correct"], n)
        lenient_ci = wilson_score_interval(st["lenient_correct"], n)
        summary_table.append({
            "config": cfg,
            "strict_correct": st["strict_correct"],
            "lenient_correct": st["lenient_correct"],
            "total": n,
            "strict_accuracy": round(st["strict_correct"] / n, 4) if n > 0 else 0.0,
            "strict_ci_95": strict_ci,
            "lenient_accuracy": round(st["lenient_correct"] / n, 4) if n > 0 else 0.0,
            "lenient_ci_95": lenient_ci,
            "avg_latency_ms": round(st["total_latency_ms"] / n, 1) if n > 0 else 0.0,
            "avg_tokens": round(st["total_tokens"] / n, 1) if n > 0 else 0.0,
            "avg_retries": round(st["total_retries"] / n, 2) if n > 0 else 0.0,
        })

    summary = {
        "dataset": dataset_name,
        "sample_size": n,
        "groq_fallback_disabled": True,
        "table": summary_table,
        "paired_comparisons_strict": paired_comparisons_strict,
        "paired_comparisons_lenient": paired_comparisons_lenient,
        "details": ablation_stats,
    }

    # Save to run_4 exclusively
    out_file = os.path.join(RUN4_DIR, "ablation_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Ablation Study Summary ===")
    print(f"{'Config':<55} | {'Strict Acc':<12} | {'Strict 95% CI':<15} | {'Lenient Acc':<12} | {'Lenient 95% CI'}")
    print("-" * 125)
    for row in summary_table:
        s_ci = f"[{row['strict_ci_95'][0]}%, {row['strict_ci_95'][1]}%]"
        l_ci = f"[{row['lenient_ci_95'][0]}%, {row['lenient_ci_95'][1]}%]"
        print(f"{row['config']:<55} | {row['strict_accuracy']*100:>10.1f}% | {s_ci:<15} | {row['lenient_accuracy']*100:>11.1f}% | {l_ci:<15}")
    print(f"\nSaved results to {out_file}")

    return summary


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl"
    q_count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    provider = sys.argv[3] if len(sys.argv) > 3 else "groq"
    asyncio.run(run_ablation_study(dataset_name=split, max_questions=q_count, provider_name=provider))
