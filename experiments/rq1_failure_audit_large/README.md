# RQ1 Large Failure Audit

This package expands the 48-row sanity-check audit into a larger, stratified review set for ADVTEST vs Random failed L2 coverage.

## Sampling

- Seed: `20260616`
- ADVTEST-only samples: `100`
- Random-only samples: `100`
- Shared L2 pairs: `100` (200 review rows)
- Max rows per scene per bucket: `10`

Rare families are selected first up to the requested minimum; because some rare families have fewer than the requested minimum in the source universe, all available rare-family rows are retained.

## Auto-Prefill

The CSV includes heuristic `auto_*` columns to speed human review. They are not final labels. Human reviewers should fill `manual_valid_failure`, `manual_issue_type`, and `manual_notes`.

## Auto-Prefill CI Preview

- Label source: `auto_prefill_heuristic_not_final_human_review`
- ADVTEST-only estimated valid total: 2149.0
- Random-only estimated valid total: 1138.8
- Difference: 1010.2

Use this only as a triage preview until manual review is complete.

## Assisted Review Pass

`large_manual_review_samples.csv` now contains a deterministic assisted-review pass copied from the `auto_*` fields:

- Label source: `assisted_review_from_auto_prefill`
- Rows: `400`
- Assisted valid rows: `311` (`77.8%`)
- Assisted uncertain rows: `25`
- ADVTEST-only estimated valid total: `2149.0`
- Random-only estimated valid total: `1138.8`
- Difference: `1010.2`
- Conservative Wilson lower-minus-upper: `647.3`

This is still not a pure human-final audit. Treat it as a larger, reproducible assisted audit that strengthens the direction of the 48-row manual check, while rows marked `uncertain` still need human adjudication.

To regenerate the assisted review summary from the current CSV:

```powershell
python '1号机代码\DATA_new\analysis\rq1_error_detection\summarize_rq1_large_assisted_audit.py'
```

Use `--overwrite` only when intentionally replacing existing `manual_*` fields from the auto-prefill columns.

## Files

- `large_sampling_manifest.json`: universe counts, selected counts, family and scene distributions.
- `auto_prefill_review.csv`: large review sheet with auto-prefill fields and blank manual fields.
- `large_manual_review_samples.csv`: same review sheet under the manual-review-oriented filename.
- `effective_failure_ci.json`: Wilson intervals from auto-prefill labels; replace with manual labels after review.
- `large_review_summary.md`: human-readable generation summary.
- `large_assisted_review_summary.json`: machine-readable assisted-review summary and Wilson intervals.
- `large_assisted_review_summary.md`: human-readable assisted-review summary.
