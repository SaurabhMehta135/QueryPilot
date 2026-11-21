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