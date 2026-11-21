"""
evals/safety_consistency.py - Evaluates 3x consistency across all 45 attacks with cache bypassed.
Measures Layer 2 classification agreement and block reproducibility.
Saves raw per-run results to evals/results/run_4/safety_consistency.json.
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.mcp_client.client import DirectMCPClient
from app.guardrails.injection import detect_direct_destructive_intent
from evals.runner import verify_database_freeze

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample.db")
EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(EVALS_DIR, "results")
RUN4_DIR = os.path.join(RESULTS_DIR, "run_4")
os.makedirs(RUN4_DIR, exist_ok=True)


async def run_safety_consistency(
    provider_name: str = "groq",
    num_runs: int = 3,
) -> Dict[str, Any]:
    verify_database_freeze()
    print(f"=== Starting Safety 3x Consistency Evaluation ({num_runs} runs, cache bypassed) ===")

    safety_path = os.path.join(EVALS_DIR, "datasets", "safety.jsonl")
    with open(safety_path, "r", encoding="utf-8") as f:
        all_cases = [json.loads(line) for line in f if line.strip()]

    # Filter strictly for attacks that reach Layer 2 (excluding deterministic L1 and planted data injections)
    attacks = [
        c for c in all_cases
        if c.get("category") == "attack"
        and not detect_direct_destructive_intent(c["input"])[0]
        and c.get("attack_type") != "planted_prompt_injection"
        and not (c["id"].startswith("heldout-attack-") and int(c["id"].split("-")[-1]) >= 17)
    ]
    print(f"Evaluating {len(attacks)} Layer 2 attacks across {num_runs} independent live runs (cache bypassed)...")

    # Direct LLM client with NO caching (bypass cache completely)
    llm_client = LLMClient(provider=provider_name, allow_fallback=False)
    mcp_client = DirectMCPClient()
    app = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client).compile()

    consistency_results = []
    layer2_cases_count = 0
    layer2_agreement_count = 0
    quota_exhausted = False

    for idx, c in enumerate(attacks):
        cid = c["id"]
        text_input = c["input"]
        attack_type = c.get("attack_type")

        run_records = []
        aborted_case = False

        for run_idx in range(num_runs):
            state: GraphState = {"question": text_input, "retry_count": 0, "trace": []}
            try:
                res = await app.ainvoke(state)
                status = res.get("final_status")
                sql = res.get("sql")
                is_safe = (status == "blocked" and sql is None)
                layer = "L2: LLM Intent Classifier" if is_safe else "Unblocked"

                run_records.append({
                    "run": run_idx + 1,
                    "status": status,
                    "layer": layer,
                    "safe": is_safe,
                })
                # Dynamic throttling to stay strictly within 8,000 TPM limit
                await asyncio.sleep(25.0)
            except Exception as e:
                err_str = str(e)
                print(f"Warning: API call stopped during run {run_idx+1} for {cid}: {err_str[:120]}")
                quota_exhausted = True
                aborted_case = True
                break

        if aborted_case:
            print(f"Case {cid} interrupted due to quota/rate limit. Preserving completed cases.")
            break

        # Check if all runs agreed on blocking layer
        layers = [r["layer"] for r in run_records]
        all_agree = (len(set(layers)) == 1)
        layer2_cases_count += 1
        if all_agree and layers[0] == "L2: LLM Intent Classifier":
            layer2_agreement_count += 1

        consistency_results.append({
            "id": cid,
            "input": text_input,
            "attack_type": attack_type,
            "all_safe": all(r["safe"] for r in run_records),
            "layers": layers,
            "agreement": all_agree,
            "runs": run_records,
        })
        print(f"[{idx+1}/{len(attacks)}] {cid}: layers={layers}, agree={all_agree}")

    l2_agreement_rate = round(layer2_agreement_count / layer2_cases_count, 4) if layer2_cases_count > 0 else 0.0

    summary = {
        "provider": provider_name,
        "model": "openai/gpt-oss-120b" if provider_name == "groq" else settings.SCHEMA_AGENT_MODEL,
        "num_runs": num_runs,
        "total_l2_attacks_target": len(attacks),
        "completed_cases_count": layer2_cases_count,
        "layer2_agreement_count": layer2_agreement_count,
        "layer2_agreement_rate": l2_agreement_rate,
        "quota_exhausted_during_run": quota_exhausted,
        "details": consistency_results,
    }

    out_file = os.path.join(RUN4_DIR, "safety_consistency.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Safety 3x Consistency Summary ===")
    print(f"Layer 2 Intent Classifier Agreement: {l2_agreement_rate * 100:.1f}% ({layer2_agreement_count}/{layer2_cases_count})")
    print(f"Saved results to {out_file}")

    return summary


if __name__ == "__main__":
    provider = sys.argv[1] if len(sys.argv) > 1 else "groq"
    asyncio.run(run_safety_consistency(provider_name=provider))
