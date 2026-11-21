import json

with open('evals/results/accuracy_dev.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

details = d.get('details', [])
failed = [r for r in details if not r.get('is_correct')]

print(f"Total failed dev questions: {len(failed)}")

def categorize(r):
    q = r['question'].lower()
    gen = (r.get('generated_sql') or '').lower()
    ref = (r.get('reference_sql') or '').lower()
    
    if ('state' in gen or 'state' in ref) and any(abbr in ref for abbr in ["'ca'", "'fl'", "'ny'", "'tx'"]):
        return "State code format mismatch (full state name vs 2-letter abbreviation)"
    if 'payment_method' in ref and any(pm in ref for pm in ["'credit_card'", "'paypal'", "'bank_transfer'"]):
        if "'credit card'" in gen or "'paypal'" not in gen:
            return "Payment method enum mismatch (credit card vs credit_card)"
    if "status = 'completed'" in ref and "status = 'completed'" not in gen:
        return "Hidden filter assumption: unstated status='completed' required by reference"
    if "status = 'successful'" in ref and "status = 'successful'" not in gen:
        return "Hidden filter assumption: unstated status='successful' required by reference"
    if len(r.get('gen_row_count', 0) if isinstance(r.get('gen_row_count'), list) else [1]) != len(r.get('ref_row_count', 0) if isinstance(r.get('ref_row_count'), list) else [1]):
        pass
    if 'group by' in ref and 'group by' in gen:
        return "Aggregation grouping / having nuance"
    if 'julianday' in ref or 'strftime' in ref:
        return "Date/time calculation nuance"
    return "Query logic / subquery join difference"

for r in failed:
    cat = categorize(r)
    r['root_cause'] = cat
    print(f"{r['id']} ({r['difficulty']}): {cat}")

lines = [
    '| ID | Diff | Question | Generated SQL | Reference SQL | Root Cause Category |',
    '|---|---|---|---|---|---|',
]

for r in failed:
    cat = r['root_cause']
    q = r['question'].replace('|', '\\|')
    gen = (r.get('generated_sql') or '').replace('|', '\\|').replace('\n', ' ')
    ref = (r.get('reference_sql') or '').replace('|', '\\|').replace('\n', ' ')
    qid = r['id']
    diff = r.get('difficulty')
    lines.append(f"| `{qid}` | {diff} | {q} | `{gen}` | `{ref}` | {cat} |")

with open('evals/dev_failure_analysis_table.md', 'w', encoding='utf-8') as out:
    out.write('\n'.join(lines) + '\n')

print(f"Wrote {len(lines)-2} failed queries to evals/dev_failure_analysis_table.md")
