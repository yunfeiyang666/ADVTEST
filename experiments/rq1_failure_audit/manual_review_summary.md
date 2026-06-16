# RQ1 Manual Failure Audit Summary

## Overall

- Reviewed rows: 48
- Valid visual/structural failures: 33 (68.8%)
- Invalid or uncertain rows: 15

## By Bucket

| bucket | total | valid_yes | valid_no | uncertain | valid_rate |
|---|---|---|---|---|---|
| advtest_only_l2 | 12 | 8 | 4 | 0 | 66.7% |
| random_only_l2 | 12 | 9 | 3 | 0 | 75.0% |
| shared_l2_advtest | 12 | 8 | 4 | 0 | 66.7% |
| shared_l2_random | 12 | 8 | 4 | 0 | 66.7% |

## By Method

| method | total | valid_yes | valid_no | uncertain | valid_rate |
|---|---|---|---|---|---|
| advtest | 24 | 16 | 8 | 0 | 66.7% |
| random | 24 | 17 | 7 | 0 | 70.8% |

## Issue Types

- answer_granularity_mismatch: 15
- valid_visual_or_structural_error: 33

## Paper Use

Use the valid-rate numbers as a qualitative audit of sampled failures. Rows marked `answer_granularity_mismatch` should be reported as a scoring / answer-format boundary, not as strong visual-model failures.
