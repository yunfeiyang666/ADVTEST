# RQ1 Failure Audit Pack

This directory samples concrete call1000 mPLUG failures for manual inspection. It focuses on ADVTEST vs Random because this is the coverage-comparable internal ablation.

## Overlap Summary

| level | advtest_count | random_count | advtest_only | random_only | shared |
|---|---|---|---|---|---|
| question_failure_signature | 981 | 912 | 704 | 635 | 277 |
| frame_qualified_failed_l2 | 4488 | 2727 | 3070 | 1309 | 1418 |

## Interpretation

- `question_failure_signature` compares failed questions after frame-qualifying structural L2 items.
- `frame_qualified_failed_l2` compares the structural L2 items touched by failed questions. This is the better lens for checking whether ADVTEST finds broader structural error space.
- Manual review should focus first on `advtest_only_l2` samples, then inspect `shared_l2` pairs to compare how the two methods expose the same structural miss.

## Manual Review Protocol

Open `manual_review_samples.csv` and fill:

- `manual_valid_failure`: yes / no / uncertain
- `manual_issue_type`: one of `valid_visual_or_structural_error`, `answer_granularity_mismatch`, `ambiguous_question`, `mosaic_or_label_artifact`, `lexical_scoring_artifact`, `other`
- `manual_notes`: short evidence from the image and text

## Generated Files

- `failure_audit.json`: complete structured audit payload.
- `failure_overlap_summary.csv`: overlap counts.
- `manual_review_samples.csv`: deterministic samples for human review.

## Reproduction

Run from repository root:

```powershell
$codeRoot = (Get-ChildItem -Directory | Where-Object Name -Like '1*' | Select-Object -First 1).FullName
$script = Join-Path $codeRoot 'DATA_new\analysis\rq1_error_detection\build_rq1_failure_audit.py'
python $script
```
