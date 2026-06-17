# RQ1 Human Adjudication Pack

This file describes the calibration subset for checking the 400-row assisted failure audit.

## Sampling Policy

- Seed: `20260616`
- Target rows: `100`
- Include all rows whose assisted label is `uncertain`.
- Per bucket, sample up to `8` assisted `no` rows, then fill with assisted `yes` rows.
- Scene cap after uncertain rows: `4` per bucket.

## Selected Counts

- Rows: `100`
- By label: `{'no': 32, 'uncertain': 25, 'yes': 43}`
- By selection reason: `{'all_uncertain': 25, 'stratified_assisted_no': 32, 'stratified_assisted_yes': 43}`
- By bucket and label: `{'advtest_only_l2 | no': 8, 'advtest_only_l2 | uncertain': 6, 'advtest_only_l2 | yes': 11, 'random_only_l2 | no': 8, 'random_only_l2 | uncertain': 3, 'random_only_l2 | yes': 14, 'shared_l2_advtest | no': 8, 'shared_l2_advtest | uncertain': 8, 'shared_l2_advtest | yes': 9, 'shared_l2_random | no': 8, 'shared_l2_random | uncertain': 8, 'shared_l2_random | yes': 9}`

## Human Review Instructions

Fill only the `human_*` columns. Treat the existing `manual_*` columns as assisted labels from auto-prefill, not final human labels.

- `human_valid_failure`: `yes`, `no`, or `uncertain`.
- `human_issue_type`: reuse the existing issue taxonomy.
- `human_agrees_with_assisted`: `yes` if the human label matches `manual_valid_failure`, otherwise `no`.
- `human_notes`: short reason, especially for disagreements.

## Completion Gate

After annotation, regenerate and validate the human-calibrated artifacts:

```powershell
$codeRoot = (Get-ChildItem -Directory | Where-Object Name -Like '1*' | Select-Object -First 1).FullName
python (Join-Path $codeRoot 'DATA_new\analysis\rq1_error_detection\summarize_rq1_human_adjudication.py') --require-complete
python (Join-Path $codeRoot 'DATA_new\analysis\rq1_error_detection\validate_rq1_failure_audit_artifacts.py') --require-human-complete
```

If either command fails, keep the audit language as `pending human review` and fix the reported row before using calibrated estimates.
