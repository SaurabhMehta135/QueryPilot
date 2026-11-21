import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.cache import compute_cache_key, get_cached_response
from app.agents.prompt_loader import load_prompt

dev_path = "evals/datasets/dev.jsonl"
with open(dev_path, "r", encoding="utf-8") as f:
    questions = [json.loads(line) for line in f if line.strip()]

print(f"Total dev questions: {len(questions)}")
# Check accuracy_dev.json from run_1_original or previous runs
run1_path = "evals/results/run_1_original/accuracy_dev.json"
if os.path.exists(run1_path):
    with open(run1_path, "r", encoding="utf-8") as f:
        run1 = json.load(f)
    print(f"Run 1 dev results had {len(run1.get('details', []))} questions, overall accuracy: {run1.get('overall_execution_accuracy')}")
