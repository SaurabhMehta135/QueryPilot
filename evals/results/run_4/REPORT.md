# QueryPilot Phase 8 Evaluation Report (run_4)

**Evaluation Tag:** `eval-freeze-v1`  
**Primary Model:** `openai/gpt-oss-120b` (Groq on-demand) / `gemini-3.1-flash-lite`  
**Fallback Model:** Disabled during benchmark evals (`allow_fallback=False`)  
**Run Directory:** `evals/results/run_4/`  

---

## 1. Frozen Code & Dataset Hashes (eval-freeze-v1)

| Asset Type | File Path | SHA-256 Checksum |
|---|---|---|
| **Database** | `data/sample.db` | `2546fe654e375e3721c9e3593f0baf357649866eedaae0dc1b63149ee6f08961` |
| **Dev Dataset (Original)** | `evals/datasets/dev_original.jsonl` | `b881863b123fc9e3ff1e0a5d1d3b4e7a984acc50d984ab22c34cc284726694a0` |
| **Dev Dataset (Revised)** | `evals/datasets/dev.jsonl` | `5e30531c79c2ce8df8d44b1bbcf698afc20b76cc1ff19a52a63f13ffb3de594a` |
| **Test Dataset (Original)** | `evals/datasets/test_original.jsonl` | `fbd60251e23e529cfc4b501a98a7b6e38dcbe4729148b099d06170f37fe3d2e2` |
| **Test Dataset (Audited)** | `evals/datasets/test.jsonl` | `5ce109b421be74fe2ae056287d5db95422368f83d1d8cfbd829e24dbbc0129e7` |
| **Prompt: Schema Agent** | `prompts/schema_agent.md` | `c055705c670daa536883768e666baf52d3a68c4860bc8ee4a3b6e925db062429` |
| **Prompt: SQL Writer** | `prompts/sql_writer.md` | `67e3297f1a195cf18121c52613c4224096b8fddfa8a9c91cade17270004c4e8d` |
| **Prompt: SQL Repair** | `prompts/sql_repair.md` | `8c8b049cff4b52aa1cfeea97828d34bddb9bfbc8af1d6a7f34e3a9c11aa84926` |
| **Prompt: Explainer** | `prompts/explainer.md` | `156d0f0621d9775c07fdd200f890d5a112ef486117d6583d9133147d395a45ab` |
| **Scoring Engine** | `evals/runner.py` | `35cbcdbf4655b65d3d1f9052d3f1e271ce00eca4d8e7a49198cd408c596aa3d9` |
| **Dev Rescorer** | `evals/rescore_dev.py` | `e3a80cb786515a9e349685fd5a42bd847772bff2bc4e1f99bcbe8afd8c1cf0fc` |

---

## 2. Comparator Rules & Definitions

1. **Strict Scoring (`compare_results_strict`):**
   - Exact same number of columns as reference SQL.
   - Exact same number of rows as reference SQL.
   - **Column-order-insensitive:** Evaluates all permutations of generated column projections.
   - **Numeric tolerance:** Float values rounded to 2 decimal places before comparison.
   - **Order sensitivity:** Respects `order_matters` flag (`True` requires exact row sequence match; `False` uses multiset equality via `collections.Counter`).

2. **Lenient Scoring (`compare_results_lenient`):**
   - Generated query must project at least the number of columns in reference (n_gen >= n_ref).
   - Exact same number of rows as reference SQL.
   - **Projection subset:** Evaluates permutations of size k=n_ref from the generated columns to find an exact match with reference rows.
   - **Numeric tolerance:** Float values rounded to 2 decimal places.
   - **Order sensitivity:** Respects `order_matters` flag (`True` requires exact row sequence match; `False` uses multiset equality).

---

## 3. Dev Set Accuracy Progression Bridge (50 Questions)

*Note: Reference modifications represent dataset corrections performed after reviewing dev set reference assumptions, not model improvements.*

| Evaluation Stage | Strict Accuracy | Lenient Accuracy | Primary Causal Factor |
|---|---|---|---|
| **1. Run 3 Comparator** (Original refs) | **56.0%** (28/50) [42.3%, 68.8%] | **76.0%** (38/50) [62.6%, 85.7%] | Baseline evaluation using exact column order and strict float comparison. |
| **2. New Comparator** (Original refs) | **62.0%** (31/50) [48.2%, 74.1%] | **76.0%** (38/50) [62.6%, 85.7%] | **Comparator Fix (+6.0% strict):** Column-order insensitivity and 2-decimal float tolerance (`easy-020`, `easy-022`, `med-007`). |
| **3. Revised References** (New comparator) | **70.0%** (35/50) [56.2%, 80.9%] | **84.0%** (42/50) [71.5%, 91.7%] | **Dataset Reference Corrections (+8.0% strict, +8.0% lenient):** Corrected debatable assumptions (`med-015`, `med-022`, `hard-001`, `hard-006`). |

*(Note on `hard-008`: If unrequested `order_matters: true` is relaxed to `false`, Strict reaches 36/50 = 72.0% [58.3%, 82.5%] and Lenient reaches 43/50 = 86.0% [73.8%, 93.0%]).*

---

## 4. Dev Set 50-Row Per-Question Rescore Table

| # | Question ID | Difficulty | Old-Ref Strict | Old-Ref Lenient | New-Ref Strict | New-Ref Lenient | Scorer Difference Reason |
|---|---|---|---|---|---|---|---|
| 1 | easy-001 | easy | PASS | PASS | PASS | PASS | - |
| 2 | easy-002 | easy | PASS | PASS | PASS | PASS | - |
| 3 | easy-003 | easy | PASS | PASS | PASS | PASS | - |
| 4 | easy-004 | easy | PASS | PASS | PASS | PASS | - |
| 5 | easy-005 | easy | PASS | PASS | PASS | PASS | - |
| 6 | easy-006 | easy | PASS | PASS | PASS | PASS | - |
| 7 | easy-007 | easy | PASS | PASS | PASS | PASS | - |
| 8 | easy-008 | easy | PASS | PASS | PASS | PASS | - |
| 9 | easy-009 | easy | PASS | PASS | PASS | PASS | - |
| 10 | easy-010 | easy | PASS | PASS | PASS | PASS | - |
| 11 | easy-011 | easy | PASS | PASS | PASS | PASS | - |
| 12 | easy-012 | easy | PASS | PASS | PASS | PASS | - |
| 13 | easy-013 | easy | PASS | PASS | PASS | PASS | - |
| 14 | easy-014 | easy | PASS | PASS | PASS | PASS | - |
| 15 | easy-015 | easy | PASS | PASS | PASS | PASS | - |
| 16 | easy-016 | easy | PASS | PASS | PASS | PASS | - |
| 17 | easy-017 | easy | PASS | PASS | PASS | PASS | - |
| 18 | hard-001 | hard | FAIL | FAIL | PASS | PASS | Reference aligned Q2 - Q1 sign convention (flips to PASS under both) |
| 19 | hard-002 | hard | PASS | PASS | PASS | PASS | - |
| 20 | hard-003 | hard | FAIL | FAIL | FAIL | FAIL | - |
| 21 | hard-004 | hard | FAIL | FAIL | FAIL | FAIL | - |
| 22 | hard-005 | hard | FAIL | FAIL | FAIL | FAIL | - |
| 23 | hard-006 | hard | FAIL | FAIL | PASS | PASS | Reference dropped unrequested prev_month_revenue (flips to PASS under both) |
| 24 | hard-007 | hard | PASS | PASS | PASS | PASS | - |
| 25 | hard-008 | hard | FAIL | FAIL | FAIL | FAIL | Model lacks ORDER BY; fails under order_matters=True (passes both if false) |
| 26 | hard-009 | hard | FAIL | FAIL | FAIL | FAIL | - |
| 27 | hard-010 | hard | FAIL | FAIL | FAIL | FAIL | - |
| 28 | hard-011 | hard | PASS | PASS | PASS | PASS | - |
| 29 | med-001 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 30 | med-002 | medium | PASS | PASS | PASS | PASS | - |
| 31 | med-003 | medium | PASS | PASS | PASS | PASS | - |
| 32 | med-004 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 33 | med-005 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 34 | med-006 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 35 | med-007 | medium | PASS | PASS | PASS | PASS | - |
| 36 | med-008 | medium | PASS | PASS | PASS | PASS | - |
| 37 | med-009 | medium | PASS | PASS | PASS | PASS | - |
| 38 | med-010 | medium | PASS | PASS | PASS | PASS | - |
| 39 | med-011 | medium | PASS | PASS | PASS | PASS | - |
| 40 | med-012 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 41 | med-013 | medium | PASS | PASS | PASS | PASS | - |
| 42 | med-014 | medium | PASS | PASS | PASS | PASS | - |
| 43 | med-015 | medium | FAIL | FAIL | PASS | PASS | Reference dropped COUNT and unrequested ORDER BY (flips to PASS under both) |
| 44 | med-016 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 45 | med-017 | medium | FAIL | FAIL | FAIL | FAIL | - |
| 46 | med-018 | medium | FAIL | FAIL | FAIL | FAIL | - |
| 47 | med-019 | medium | PASS | PASS | PASS | PASS | - |
| 48 | med-020 | medium | FAIL | PASS | FAIL | PASS | Model returns extra projection columns (lenient allows subset, strict requires exact) |
| 49 | med-021 | medium | PASS | PASS | PASS | PASS | - |
| 50 | med-022 | medium | FAIL | FAIL | PASS | PASS | Reference dropped unrequested state column (flips to PASS under both) |

---

## 5. Test Set Reference Audit by Rule (5 Modified References)

All references in `evals/datasets/test.jsonl` were audited purely by rule (sign convention, unrequested metadata/filter columns, and customer ID projection consistency) without inspecting any model outputs on the test set. Original test references are preserved in `evals/datasets/test_original.jsonl`.

1. **`hard-012`**: Dropped unrequested filter aggregates (`orders_count`, `avg_val`) and customer names; projects `c.customer_id` only.
2. **`hard-015`**: Dropped unrequested customer names (`first_name`, `last_name`); projects `c.customer_id` only.
3. **`med-032`**: Dropped unrequested filter column `COUNT(r.review_id) AS reviews`; projects `p.name, avg_rating`.
4. **`hard-028`**: Dropped unrequested customer names (`first_name`, `last_name`); projects `c.customer_id, spend`.
5. **`hard-034`**: Dropped unrequested group size `COUNT(*) AS count`; projects `order_type, aov`.

---

## 6. Prompt Resolution & Single Source of Truth

- **Prompt Loader Implementation:** `app/agents/prompt_loader.py` dynamically resolves: `PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'prompts'))`
- **Resolution Result:** `prompts/` in repository root. No duplicate directory `app/agents/prompts/` exists.
- **Single Source of Truth:** `prompts/schema_agent.md` (`SHA-256: c055705c670daa536883768e666baf52d3a68c4860bc8ee4a3b6e925db062429`).

---

## 7. Safety Suite & Non-Write Payloads Analysis

### 7.1 Analysis of 8 Non-Write Payloads on Read-Only Connection

| Payload Statement | Classification | Execution Result on `mode=ro` | Interception Layer in QueryPilot |
|---|---|---|---|
| `DROP VIEW IF EXISTS active_products;` | DDL Statement | No-op (view does not exist). If existed, blocked by `mode=ro`. | **Layer 3 (SQL AST Validator):** Prohibited node `exp.Drop` |
| `TRUNCATE TABLE payments;` | Invalid Dialect Syntax | Blocked by SQLite parser (`syntax error near "TRUNCATE"`). | **Layer 3 (SQL AST Validator):** Dialect parsing error / `exp.Command` |
| `PRAGMA table_info(customers);` | Read Metadata | Read-only metadata query; alters zero state. | **Layer 3 (SQL AST Validator):** Prohibited node `exp.Pragma` |
| `PRAGMA foreign_keys = OFF;` | PRAGMA Toggle | Read/toggle pragma; creates no files, modifies zero data. | **Layer 3 (SQL AST Validator):** Prohibited node `exp.Pragma` |
| `ATTACH DATABASE 'malicious.db' AS evil;` | External DB Attachment | Blocked by SQLite authorizer (`DatabaseError: not authorized`). | **Layer 3 (SQL AST Validator):** Prohibited node `exp.Command` |
| `DETACH DATABASE evil;` | External DB Detachment | Blocked by SQLite authorizer (`DatabaseError: not authorized`). | **Layer 3 (SQL AST Validator):** Prohibited node `exp.Command` |
| `SELECT * FROM sqlite_master;` | Internal Schema Access | Read-only schema query; alters zero state. | **Layer 3 (SQL AST Validator):** Forbidden internal table |
| `SELECT * FROM sqlite_schema;` | Internal Schema Access | Read-only schema query; alters zero state. | **Layer 3 (SQL AST Validator):** Forbidden internal table |

### 7.2 Proof of Filesystem Integrity
SQLite connections opened via `get_readonly_connection()` enforce `conn.set_authorizer(readonly_authorizer)` which denies `SQLITE_ATTACH` and `SQLITE_DETACH`. This guarantees that even if Layer 3 were completely bypassed, SQLite aborts query compilation before invoking the operating system's file creation API, ensuring zero external database files (`malicious.db`) are created on disk. Verified deterministically by `test_non_write_payloads_filesystem_integrity()`.

---

## 8. Operational Statistics (Uncached Only)

not measured (Test set and ablation not yet executed per freeze protocol)

---
*Report generated for QueryPilot eval-freeze-v1.*