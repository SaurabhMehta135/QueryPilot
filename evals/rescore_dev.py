import json
import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evals.runner import compare_results_strict, compare_results_lenient, wilson_score_interval

DB_PATH = "data/sample.db"
conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
cur = conn.cursor()

# Load generated SQL from run_3 dev results
with open("evals/results/run_3/accuracy_dev.json", "r", encoding="utf-8") as f:
    dev_run = json.load(f)
generated_map = {r["id"]: r.get("generated_sql") for r in dev_run["details"]}

# Load original dev references
with open("evals/datasets/dev_original.jsonl", "r", encoding="utf-8") as f:
    orig_cases = [json.loads(l) for l in f if l.strip()]

# Load revised dev references
with open("evals/datasets/dev.jsonl", "r", encoding="utf-8") as f:
    rev_cases = [json.loads(l) for l in f if l.strip()]

orig_map = {c["id"]: c for c in orig_cases}
rev_map = {c["id"]: c for c in rev_cases}

res_orig = []
res_rev = []
changed_questions = []

for qid, orig_item in orig_map.items():
    rev_item = rev_map[qid]
    gen_sql = generated_map.get(qid)
    orig_order_matters = orig_item.get("order_matters", False)
    rev_order_matters = rev_item.get("order_matters", False)

    # Execute original reference SQL
    cur.execute(orig_item["reference_sql"])
    orig_ref_rows = cur.fetchall()

    # Execute revised reference SQL
    cur.execute(rev_item["reference_sql"])
    rev_ref_rows = cur.fetchall()

    # Execute generated SQL if present
    gen_rows = None
    if gen_sql:
        try:
            cur.execute(gen_sql)
            gen_rows = cur.fetchall()
        except Exception:
            gen_rows = None

    orig_strict = compare_results_strict(gen_rows, orig_ref_rows, order_matters=orig_order_matters) if gen_rows is not None else False
    orig_lenient = compare_results_lenient(gen_rows, orig_ref_rows, order_matters=orig_order_matters) if gen_rows is not None else False

    rev_strict = compare_results_strict(gen_rows, rev_ref_rows, order_matters=rev_order_matters) if gen_rows is not None else False
    rev_lenient = compare_results_lenient(gen_rows, rev_ref_rows, order_matters=rev_order_matters) if gen_rows is not None else False

    res_orig.append({"id": qid, "strict": orig_strict, "lenient": orig_lenient})
    res_rev.append({"id": qid, "strict": rev_strict, "lenient": rev_lenient})

    if (orig_strict != rev_strict) or (orig_lenient != rev_lenient):
        changed_questions.append({
            "id": qid,
            "question": rev_item["question"],
            "orig_strict": orig_strict,
            "rev_strict": rev_strict,
            "orig_lenient": orig_lenient,
            "rev_lenient": rev_lenient,
            "generated_sql": gen_sql,
            "orig_ref_sql": orig_item["reference_sql"],
            "rev_ref_sql": rev_item["reference_sql"],
        })

n = len(res_orig)
orig_s_cnt = sum(1 for r in res_orig if r["strict"])
orig_l_cnt = sum(1 for r in res_orig if r["lenient"])
rev_s_cnt = sum(1 for r in res_rev if r["strict"])
rev_l_cnt = sum(1 for r in res_rev if r["lenient"])

orig_s_ci = wilson_score_interval(orig_s_cnt, n)
orig_l_ci = wilson_score_interval(orig_l_cnt, n)
rev_s_ci = wilson_score_interval(rev_s_cnt, n)
rev_l_ci = wilson_score_interval(rev_l_cnt, n)

table_50 = []
for qid in sorted(orig_map.keys()):
    orig_res = next(r for r in res_orig if r["id"] == qid)
    rev_res = next(r for r in res_rev if r["id"] == qid)
    diff = rev_map[qid]["difficulty"]
    table_50.append({
        "question_id": qid,
        "difficulty": diff,
        "old_strict": orig_res["strict"],
        "old_lenient": orig_res["lenient"],
        "new_strict": rev_res["strict"],
        "new_lenient": rev_res["lenient"],
    })

out = {
    "sample_size": n,
    "original": {
        "strict_correct": orig_s_cnt,
        "strict_pct": round(orig_s_cnt / n * 100, 1),
        "strict_ci_95": orig_s_ci,
        "lenient_correct": orig_l_cnt,
        "lenient_pct": round(orig_l_cnt / n * 100, 1),
        "lenient_ci_95": orig_l_ci,
    },
    "revised": {
        "strict_correct": rev_s_cnt,
        "strict_pct": round(rev_s_cnt / n * 100, 1),
        "strict_ci_95": rev_s_ci,
        "lenient_correct": rev_l_cnt,
        "lenient_pct": round(rev_l_cnt / n * 100, 1),
        "lenient_ci_95": rev_l_ci,
    },
    "changed_questions": changed_questions,
    "table_50": table_50,
}

print(json.dumps({k: v for k, v in out.items() if k != "table_50"}, indent=2))

with open("evals/results/run_4/dev_rescore_comparison.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
