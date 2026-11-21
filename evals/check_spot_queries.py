import json
import sqlite3

conn = sqlite3.connect("file:data/sample.db?mode=ro", uri=True)
cur = conn.cursor()

with open("evals/datasets/spot_check_20.json", "r", encoding="utf-8") as f:
    data = json.load(f)["spot_checks"]

print(f"Total spot check items: {len(data)}")
for i, item in enumerate(data):
    sql = item["sql"]
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"[{i+1:02d}] ID: {item['id']} | Rows Returned: {len(rows)}")
    print(f"     Question: {item['question']}")
    print(f"     SQL: {sql}")
    sample = str(rows[:2])
    if len(sample) > 100:
        sample = sample[:100] + "..."
    print(f"     Returned Rows: {sample}")
    print()
