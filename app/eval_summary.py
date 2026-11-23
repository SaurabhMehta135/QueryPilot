"""
app/eval_summary.py - Evaluation summary aggregator.
Reads stored raw benchmark JSON artifacts and returns clean evaluation summaries
for the Evaluation Dashboard without latency or cost figures.
"""

import json
from pathlib import Path
from typing import Any, Dict


FAILURE_TAXONOMY = {
    "easy-027": ("Reference Issue", "Reference projected unrequested review_id column"),
    "med-023": ("Model Error", "Summed raw discount rates instead of dollar discount amount"),
    "med-025": ("Schema Ambiguity", "Resolved category name with category-grouped order vs category_id"),
    "med-026": ("Ambiguous Question", "Distinct line items per order vs total item units"),
    "med-033": ("Reference Issue", "Reference used unrequested DESC sort on rating 1 to 5"),
    "med-034": ("Model Error", "Summed discount rates instead of dollar discount amount"),
    "med-040": ("Reference Issue", "Reference projected unrequested distinct_categories aggregate"),
    "med-041": ("Reference Issue", "Reference projected unrequested product_count aggregate"),
    "med-043": ("Reference Issue", "Reference projected unrequested count aggregate"),
    "hard-012": ("Reference Issue", "Same 79 customers selected; failed on unrequested sort under order_matters"),
    "hard-014": ("Schema Ambiguity", "Product names projected instead of raw product IDs"),
    "hard-016": ("Model Error", "Missing filter on successful payment statuses"),
    "hard-017": ("Model Error", "Ordered by 2024 revenue instead of year-over-year revenue difference"),
    "hard-018": ("Model Error", "Thresholded over all customers rather than customers with completed orders"),
    "hard-021": ("Model Error", "Returned pivoted single-row table rather than 2-row grouped table"),
    "hard-022": ("Ambiguous Question", "Applied LIMIT 1 for single winning method vs all 4 ranked"),
}


def load_eval_summary() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    run_4 = root / "evals" / "results" / "run_4"
    safety_results_path = run_4 / "safety_results.json"
    taxonomy_path = run_4 / "failure_taxonomy.json"

    dev_json = json.load(open(run_4 / "accuracy_dev.json", encoding="utf-8"))
    test_json = json.load(open(run_4 / "accuracy_test_stratified_50.json", encoding="utf-8"))
    ablation_json = json.load(open(run_4 / "ablation_results.json", encoding="utf-8"))
    safety_results_json = json.load(open(safety_results_path, encoding="utf-8"))

    taxonomy_json = {}
    if taxonomy_path.exists():
        taxonomy_json = json.load(open(taxonomy_path, encoding="utf-8"))
    per_q_tax = taxonomy_json.get("per_question_taxonomy", {})

    # 1. Dev details (clean question rows, no latency/cost)
    dev_questions = []
    for d in dev_json.get("details", []):
        dev_questions.append({
            "id": d.get("id"),
            "difficulty": d.get("difficulty"),
            "question": d.get("question"),
            "reference_sql": d.get("reference_sql"),
            "generated_sql": d.get("generated_sql"),
            "is_correct_strict": bool(d.get("is_correct_strict")),
            "is_correct_lenient": bool(d.get("is_correct_lenient")),
            "retries": d.get("retries", 0),
            "model": d.get("model", "openai/gpt-oss-120b"),
        })

    # 2. Test details with failure classification
    test_questions = []
    for d in test_json.get("details", []):
        qid = d.get("id")
        tax_entry = per_q_tax.get(qid, {})
        fail_cat = tax_entry.get("category")
        fail_reason = tax_entry.get("reason")
        test_questions.append({
            "id": qid,
            "difficulty": d.get("difficulty"),
            "question": d.get("question"),
            "reference_sql": d.get("reference_sql"),
            "generated_sql": d.get("generated_sql"),
            "is_correct_strict": bool(d.get("is_correct_strict")),
            "is_correct_lenient": bool(d.get("is_correct_lenient")),
            "retries": d.get("retries", 0),
            "failure_category": fail_cat,
            "failure_reason": fail_reason,
            "model": d.get("model", "openai/gpt-oss-120b"),
        })

    # 3. Ablation configs (uncached tokens only, no latency/cost)
    table_configs = {item["config"]: item for item in ablation_json.get("table", [])}
    cfg_A = table_configs["Config A: Single-shot Baseline"]
    cfg_B = table_configs["Config B: Config A + Dynamic Schema Linking"]
    cfg_D = table_configs["Config D: Full QueryPilot (Self-Correction)"]

    ablation_summary = {
        "configs": [
            {
                "id": "A",
                "name": "Config A: Single-shot Baseline",
                "strict_accuracy": cfg_A["strict_accuracy"],
                "strict_correct": cfg_A["strict_correct"],
                "lenient_accuracy": cfg_A["lenient_accuracy"],
                "lenient_correct": cfg_A["lenient_correct"],
                "avg_tokens": 4541.2,
            },
            {
                "id": "B",
                "name": "Config B: Config A + Dynamic Schema Linking",
                "strict_accuracy": cfg_B["strict_accuracy"],
                "strict_correct": cfg_B["strict_correct"],
                "lenient_accuracy": cfg_B["lenient_accuracy"],
                "lenient_correct": cfg_B["lenient_correct"],
                "avg_tokens": 4445.7,
            },
            {
                "id": "D",
                "name": "Config D: Full QueryPilot (Self-Correction)",
                "strict_accuracy": cfg_D["strict_accuracy"],
                "strict_correct": cfg_D["strict_correct"],
                "lenient_accuracy": cfg_D["lenient_accuracy"],
                "lenient_correct": cfg_D["lenient_correct"],
                "avg_tokens": 4656.7,
            },
        ],
        "comparisons": [
            {
                "comparison": "Config B vs Config A",
                "paired_strict": "+10 / -2",
                "p_strict": 0.1094,
                "paired_lenient": "+4 / -2",
                "p_lenient": 0.6875,
            },
            {
                "comparison": "Config D vs Config A",
                "paired_strict": "+12 / -1",
                "p_strict": 0.0074,
                "paired_lenient": "+8 / -2",
                "p_lenient": 0.0386,
            },
            {
                "comparison": "Config D vs Config B",
                "paired_strict": "+5 / -2",
                "p_strict": 0.2188,
                "paired_lenient": "+5 / -1",
                "p_lenient": 0.3750,
            },
        ],
        "notes": {
            "p_value_disclosure": "Sign-test p-values are uncorrected for six comparisons; tuning set (dev.jsonl, n=50).",
            "validator_note": "Config C (validator only) was dropped as a safety layer with no accuracy change on 50 questions.",
        },
    }

    # 4. Safety benchmark summary (read from stored safety_results.json)
    attacks_count = safety_results_json.get("total_attacks", 60)
    attacks_blocked = safety_results_json.get("attacks_safely_handled", 60)
    benign_count = safety_results_json.get("total_benign_queries", 26)
    benign_allowed = benign_count - safety_results_json.get("false_blocks", 0)
    total_evaluated = attacks_count + benign_count

    clean_subset = test_json.get("clean_subset_33", {})

    return {
        "dev": {
            "total": dev_json["total_questions"],
            "lenient_accuracy": dev_json["lenient_execution_accuracy"],
            "lenient_correct": dev_json["lenient_correct_count"],
            "lenient_wilson_ci_95": dev_json.get("lenient_wilson_ci_95", [71.7, 91.5]),
            "strict_accuracy": dev_json["strict_execution_accuracy"],
            "strict_correct": dev_json["strict_correct_count"],
            "strict_wilson_ci_95": dev_json.get("strict_wilson_ci_95", [56.2, 80.9]),
            "by_difficulty": dev_json.get("accuracy_by_difficulty", {}),
            "questions": dev_questions,
        },
        "test": {
            "total": test_json["total_questions"],
            "lenient_accuracy": test_json["lenient_execution_accuracy"],
            "lenient_correct": test_json["lenient_correct_count"],
            "lenient_wilson_ci_95": test_json.get("lenient_wilson_ci_95", [54.2, 79.2]),
            "strict_accuracy": test_json["strict_execution_accuracy"],
            "strict_correct": test_json["strict_correct_count"],
            "strict_wilson_ci_95": test_json.get("strict_wilson_ci_95", [44.2, 70.6]),
            "by_difficulty": test_json.get("accuracy_by_difficulty", {}),
            "clean_subset_33": {
                "total": clean_subset.get("total", 33),
                "lenient_accuracy": clean_subset.get("lenient_accuracy", 0.545),
                "lenient_correct": clean_subset.get("lenient_correct", 18),
                "lenient_wilson_ci_95": clean_subset.get("lenient_wilson_ci_95", [38.0, 70.2]),
                "strict_accuracy": clean_subset.get("strict_accuracy", 0.394),
                "strict_correct": clean_subset.get("strict_correct", 13),
                "strict_wilson_ci_95": clean_subset.get("strict_wilson_ci_95", [24.7, 56.3]),
            },
            "failure_classification": taxonomy_json.get(
                "failure_categories",
                {
                    "Model Errors": 6,
                    "Reference Issues": 6,
                    "Ambiguous Questions": 2,
                    "Schema Ambiguities": 2,
                }
            ),
            "questions": test_questions,
        },
        "ablation": ablation_summary,
        "safety": {
            "total_evaluated": total_evaluated,
            "attacks_total": attacks_count,
            "attacks_blocked": attacks_blocked,
            "attacks_block_rate": safety_results_json.get("attack_pass_rate", 1.0),
            "benign_total": benign_count,
            "benign_allowed": benign_allowed,
            "benign_pass_rate": 1.0 - safety_results_json.get("false_block_rate", 0.0),
            "planted_injections_total": 5,
            "planted_injections_neutralized": 5,
            "layers": {
                "L1 deterministic pre-check": safety_results_json.get("layer_breakdown", {}).get("L1: Deterministic Pre-check", 30),
                "L2 LLM intent classifier": safety_results_json.get("layer_breakdown", {}).get("L2: LLM Intent Classifier", 25),
                "untrusted-data wrapping": safety_results_json.get("layer_breakdown", {}).get("Untrusted-Data Delimiter Wrapping", 5),
                "L3 SQL validator & L4 connection backstop": "20/20 in simulator",
            },
        },
        "metadata": {
            "benchmark_model": "Groq with a fallback chain (gpt-oss-120b, gpt-oss-20b, qwen)",
            "demo_model": "gemini-3.1-flash-lite via Gemini (Default in app/config.py; Mock provider available for deterministic offline tests)",
            "limitations": [
                "Synthetic Spider-adapted SQLite retail database (10 tables, ~150k rows). Real enterprise warehouses exhibit significantly more table joins, temporal partitioning, and dialect variations.",
                "Primary benchmark used Groq fallback chain (gpt-oss-120b, gpt-oss-20b, qwen); per-call model fallback identity was not recorded in log metadata.",
                "Ablation run was evaluated on the 50 dev set questions (tuning set), not the held-out test set.",
                "Sign-test p-values are uncorrected for multiple hypothesis testing across 6 comparisons.",
                "Latency and dollar costs were contaminated by rate-throttle backoffs and cache hits, so only token counts are reported.",
            ],
        },
    }
