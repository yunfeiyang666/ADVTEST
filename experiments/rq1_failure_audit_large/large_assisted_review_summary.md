# RQ1 Large Assisted Failure Audit Summary

## Caveat

Labels are assisted by deterministic auto-prefill heuristics. Rows marked uncertain require further human adjudication.

## Overall

- Rows: 400
- Assisted valid rows: 311 (77.8%)
- Assisted uncertain rows: 25

## By Bucket

| bucket | sample_rows | valid_yes | no | uncertain | valid_rate | wilson_95 | est_valid_total |
|---|---|---|---|---|---|---|---|
| advtest_only_l2 | 100 | 70 | 24 | 6 | 70.0% | [60.4%, 78.1%] | 2149.0 |
| random_only_l2 | 100 | 87 | 10 | 3 | 87.0% | [79.0%, 92.2%] | 1138.8 |
| shared_l2_advtest | 100 | 77 | 15 | 8 | 77.0% | [67.8%, 84.2%] | 1091.9 |
| shared_l2_random | 100 | 77 | 15 | 8 | 77.0% | [67.8%, 84.2%] | 1091.9 |

## Exclusive L2 Estimate

- ADVTEST-only estimated valid total: 2149.0
- Random-only estimated valid total: 1138.8
- Difference: 1010.2
- Conservative lower-minus-upper: 647.3

Use the conservative lower-minus-upper value as the quick stress test: if it stays positive, ADVTEST's larger exclusive L2 space remains larger even after Wilson uncertainty on assisted labels.
