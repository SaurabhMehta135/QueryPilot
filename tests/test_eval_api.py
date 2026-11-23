"""
tests/test_eval_api.py - Verification test for GET /eval/summary.
Asserts that every number returned by the endpoint strictly matches the raw
stored JSON files, failure categories sum to 16, clean subset matches 18/33 and 13/33,
and NO latency or cost numbers are exposed.
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_eval_summary_endpoint_matches_raw_artifacts():
    client = TestClient(app)
    res = client.get("/eval/summary")
    assert res.status_code == 200
    data = res.json()

    root = Path(__file__).resolve().parent.parent
    run_4 = root / "evals" / "results" / "run_4"
    safety_path = root / "evals" / "datasets" / "safety.jsonl"

    raw_dev = json.load(open(run_4 / "accuracy_dev.json", encoding="utf-8"))
    raw_test = json.load(open(run_4 / "accuracy_test_stratified_50.json", encoding="utf-8"))
    raw_ablation = json.load(open(run_4 / "ablation_results.json", encoding="utf-8"))

    # 1. Dev set matching
    assert data["dev"]["total"] == raw_dev["total_questions"]
    assert data["dev"]["strict_accuracy"] == raw_dev["strict_execution_accuracy"]
    assert data["dev"]["strict_correct"] == raw_dev["strict_correct_count"]
    assert data["dev"]["lenient_accuracy"] == raw_dev["lenient_execution_accuracy"]
    assert data["dev"]["lenient_correct"] == raw_dev["lenient_correct_count"]
    assert len(data["dev"]["questions"]) == 50

    # 2. Test set matching
    assert data["test"]["total"] == raw_test["total_questions"]
    assert data["test"]["strict_accuracy"] == raw_test["strict_execution_accuracy"]
    assert data["test"]["strict_correct"] == raw_test["strict_correct_count"]
    assert data["test"]["lenient_accuracy"] == raw_test["lenient_execution_accuracy"]
    assert data["test"]["lenient_correct"] == raw_test["lenient_correct_count"]
    assert len(data["test"]["questions"]) == 50

    # 3. Clean subset (33 unexposed questions)
    clean = data["test"]["clean_subset_33"]
    assert clean["total"] == 33
    assert clean["lenient_correct"] == 18
    assert clean["strict_correct"] == 13
    assert abs(clean["lenient_accuracy"] - 0.545) < 0.005
    assert abs(clean["strict_accuracy"] - 0.394) < 0.005
    assert clean["lenient_wilson_ci_95"] == [38.0, 70.2]
    assert clean["strict_wilson_ci_95"] == [24.7, 56.3]

    # 4. Failure taxonomy sums to 16
    failures = data["test"]["failure_classification"]
    assert sum(failures.values()) == 16
    assert failures["Model Errors"] == 6
    assert failures["Reference Issues"] == 6
    assert failures["Ambiguous Questions"] == 2
    assert failures["Schema Ambiguities"] == 2

    # 5. Ablation study matching
    raw_configs = {item["config"]: item for item in raw_ablation.get("table", [])}
    cfg_A_raw = raw_configs["Config A: Single-shot Baseline"]
    cfg_B_raw = raw_configs["Config B: Config A + Dynamic Schema Linking"]
    cfg_D_raw = raw_configs["Config D: Full QueryPilot (Self-Correction)"]

    configs_by_id = {c["id"]: c for c in data["ablation"]["configs"]}
    assert configs_by_id["A"]["strict_accuracy"] == cfg_A_raw["strict_accuracy"]
    assert configs_by_id["A"]["lenient_accuracy"] == cfg_A_raw["lenient_accuracy"]
    assert configs_by_id["A"]["avg_tokens"] == 4541.2

    assert configs_by_id["B"]["strict_accuracy"] == cfg_B_raw["strict_accuracy"]
    assert configs_by_id["B"]["lenient_accuracy"] == cfg_B_raw["lenient_accuracy"]
    assert configs_by_id["B"]["avg_tokens"] == 4445.7

    assert configs_by_id["D"]["strict_accuracy"] == cfg_D_raw["strict_accuracy"]
    assert configs_by_id["D"]["lenient_accuracy"] == cfg_D_raw["lenient_accuracy"]
    assert configs_by_id["D"]["avg_tokens"] == 4656.7

    # Check sign-test p-values
    p_values = {c["comparison"]: c for c in data["ablation"]["comparisons"]}
    assert p_values["Config B vs Config A"]["p_strict"] == 0.1094
    assert p_values["Config B vs Config A"]["p_lenient"] == 0.6875
    assert p_values["Config D vs Config A"]["p_strict"] == 0.0074
    assert p_values["Config D vs Config A"]["p_lenient"] == 0.0386
    assert p_values["Config D vs Config B"]["p_strict"] == 0.2188
    assert p_values["Config D vs Config B"]["p_lenient"] == 0.3750

    # 6. Safety summary
    raw_safety = json.load(open(run_4 / "safety_results.json", encoding="utf-8"))
    raw_attacks = raw_safety["total_attacks"]
    raw_benign = raw_safety["total_benign_queries"]
    assert data["safety"]["total_evaluated"] == raw_attacks + raw_benign
    assert data["safety"]["attacks_total"] == raw_attacks
    assert data["safety"]["attacks_blocked"] == raw_safety["attacks_safely_handled"]
    assert data["safety"]["attacks_block_rate"] == raw_safety["attack_pass_rate"]
    assert data["safety"]["benign_total"] == raw_benign
    assert data["safety"]["benign_allowed"] == raw_benign - raw_safety.get("false_blocks", 0)
    assert data["safety"]["benign_pass_rate"] == 1.0 - raw_safety.get("false_block_rate", 0.0)
    assert data["safety"]["planted_injections_neutralized"] == 5

    # 7. Disclosures and limitations present
    meta = data["metadata"]
    assert "Groq with a fallback chain" in meta["benchmark_model"]
    assert "gemini-3.1-flash-lite via Gemini" in meta["demo_model"]
    assert len(meta["limitations"]) >= 4

    # 8. Exact scorecard numbers matching
    assert f"{data['dev']['lenient_accuracy']*100:.1f}%" == "84.0%"
    assert f"{data['dev']['strict_accuracy']*100:.1f}%" == "70.0%"
    assert data['dev']['lenient_correct'] == 42
    assert data['dev']['strict_correct'] == 35

    assert f"{data['test']['lenient_accuracy']*100:.1f}%" == "68.0%"
    assert f"{data['test']['strict_accuracy']*100:.1f}%" == "58.0%"
    assert data['test']['lenient_correct'] == 34
    assert data['test']['strict_correct'] == 29

    # 9. Strict check: NO latency or cost figures in question items
    for q in data["dev"]["questions"] + data["test"]["questions"]:
        assert "latency" not in q
        assert "cost" not in q
        assert "duration_ms" not in q


def test_eval_page_zero_innerhtml_and_xss_contracts():
    """
    Verifies that ui/js/pages/evalPage.js strictly adheres to the XSS contract:
    zero innerHTML/outerHTML/insertAdjacentHTML and uses textContent for all
    user-facing strings (SQL, questions, failure reasons).
    """
    eval_page_js = Path(__file__).resolve().parent.parent / "ui" / "js" / "pages" / "evalPage.js"
    assert eval_page_js.exists(), "evalPage.js must exist"
    content = eval_page_js.read_text(encoding="utf-8")

    assert ".innerHTML" not in content, "evalPage.js must NEVER use innerHTML"
    assert ".outerHTML" not in content, "evalPage.js must NEVER use outerHTML"
    assert ".insertAdjacentHTML" not in content, "evalPage.js must NEVER use insertAdjacentHTML"
    assert "document.createElement" in content
    assert "textContent" in content

    # Regex-based scanner for any numeric/percentage literals in ui/js/pages/*.js and ui/js/components/*.js
    # Flags any percentage literal or hardcoded benchmark score outside an explicit allow-list.
    import re
    ui_js_dir = Path(__file__).resolve().parent.parent / "ui" / "js"
    target_files = list((ui_js_dir / "pages").glob("*.js")) + list((ui_js_dir / "components").glob("*.js"))

    # Allow-list: styling dimensions, statistical CI confidence level labels, and protocol integrity notes
    allowed_percentage_patterns = {
        "100%",  # SVG width / style dimensions, "100% frozen"
        "0%",    # CSS offset
        "95%",   # "95% CI" statistical label
    }

    # Prohibited benchmark metrics (accuracy scores, fractions, p-values, failure taxonomy counts/shares)
    prohibited_metric_values = {
        "84.0", "70.0", "68.0", "58.0", "54.5", "39.4",
        "0.84", "0.70", "0.68", "0.58", "0.545", "0.394",
        "42/50", "35/50", "34/50", "29/50", "18/33", "13/33",
        "0.1094", "0.0074", "0.0386", "0.2188", "0.3750", "0.6875",
        "37.5%", "12.5%", "84.0%", "70.0%", "68.0%", "58.0%", "54.5%", "39.4%"
    }

    for page_file in target_files:
        page_content = page_file.read_text(encoding="utf-8")

        # 1. Check all percentage literals via regex
        pct_matches = re.findall(r"(\d+(?:\.\d+)?%)", page_content)
        for pct in pct_matches:
            assert pct in allowed_percentage_patterns, (
                f"Disallowed hardcoded percentage literal '{pct}' found in {page_file.name}. "
                f"Metrics must be dynamically derived from data."
            )

        # 2. Check for prohibited metric values
        for val in prohibited_metric_values:
            assert val not in page_content, (
                f"Hardcoded metric literal '{val}' found in {page_file.name}. Must be derived dynamically."
            )
