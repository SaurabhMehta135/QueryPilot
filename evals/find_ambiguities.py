import json

with open('evals/datasets/dev.jsonl', 'r', encoding='utf-8') as f:
    dev = [json.loads(line) for line in f if line.strip()]

print(f"Total dev questions: {len(dev)}")
ambiguous_count = 0
for d in dev:
    q = d['question'].lower()
    ref = d['reference_sql'].lower()
    has_completed = "status = 'completed'" in ref and 'completed' not in q
    has_successful = "status = 'successful'" in ref and 'successful' not in q
    if has_completed or has_successful:
        ambiguous_count += 1
        print(f"[{d['id']}] {d['question']}")
        if has_completed:
            print("   Hidden Assumption: status = 'completed'")
        if has_successful:
            print("   Hidden Assumption: status = 'successful'")

print(f"\nTotal ambiguous questions found: {ambiguous_count}")

print("\n--- Test Set Ambiguities ---")
with open('evals/datasets/test.jsonl', 'r', encoding='utf-8') as f:
    test = [json.loads(line) for line in f if line.strip()]

ambiguous_test = 0
for d in test:
    q = d['question'].lower()
    ref = d['reference_sql'].lower()
    has_completed = "status = 'completed'" in ref and 'completed' not in q
    has_successful = "status = 'successful'" in ref and 'successful' not in q
    if has_completed or has_successful:
        ambiguous_test += 1
        print(f"[{d['id']}] {d['question']}")

print(f"Total ambiguous in test.jsonl: {ambiguous_test}")
