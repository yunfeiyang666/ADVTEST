# RQ1 Human Adjudication Runbook

This runbook is the operational checklist for converting the 100-row calibration
pack from `pending human review` to a reportable `human-calibrated` result.

Current status on 2026-06-17:

- Source audit: `large_manual_review_samples.csv`
- Calibration pack: `human_adjudication_pack.csv`
- Pack size: `100` rows
- Reviewed rows: `0`
- Pending rows: `100`
- Current report language: `pending human review`

Do not report the assisted labels as final human labels. The `manual_*` columns
in the calibration pack are copied from the deterministic assisted pass and are
included only as reference labels for agreement checking.

## Reviewer Task

Open:

```text
experiments/rq1_failure_audit_large/human_adjudication_pack.csv
```

Fill only these columns:

- `human_valid_failure`
- `human_issue_type`
- `human_agrees_with_assisted`
- `human_notes`

Do not edit:

- row identifiers
- `bucket`
- `selection_reason`
- `manual_*`
- `auto_*`
- question, answer, prediction, scene, frame, or L2 evidence columns

## Allowed Labels

Use exactly one of these values for `human_valid_failure`:

- `yes`: the VLM miss exposes a real visual or structural failure for the
  intended evidence.
- `no`: the apparent miss is not a valid failure under the audit criteria.
- `uncertain`: the row needs discussion or cannot be judged from the available
  evidence.

Use exactly one of these values for `human_issue_type`:

- `valid_visual_or_structural_error`
- `answer_granularity_mismatch`
- `ambiguous_question`
- `mosaic_or_label_artifact`
- `lexical_scoring_artifact`
- `other`

Set `human_agrees_with_assisted` to:

- `yes` when `human_valid_failure` equals `manual_valid_failure`
- `no` otherwise

Always fill `human_notes`. Keep it short, but include the reason for every
disagreement and every `uncertain` row.

## Recommended Review Order

1. Review all `manual_valid_failure=uncertain` rows first. These are the
   highest-value calibration rows because the assisted pass could not classify
   them confidently.
2. Review `manual_valid_failure=no` rows next to estimate whether the assisted
   pass is overly conservative.
3. Review `manual_valid_failure=yes` rows last to estimate whether the assisted
   pass overcounts valid failures.
4. Keep the four buckets balanced unless a row is blocked:
   `advtest_only_l2`, `random_only_l2`, `shared_l2_advtest`,
   `shared_l2_random`.

## Progress Check

From the repository root:

```powershell
python '1号机代码\DATA_new\analysis\rq1_error_detection\summarize_rq1_human_adjudication.py'
python '1号机代码\DATA_new\analysis\rq1_error_detection\validate_rq1_failure_audit_artifacts.py'
```

These commands are allowed to pass while rows are still pending. They are useful
for checking partial progress and catching malformed labels.

Expected current pre-review state:

```text
[human-adjudication-summary] status=pending_human_review reviewed=0 pending=100
[rq1-artifact-validation] status=ok large_rows=400 human_rows=100 human_pending=100
```

## Final Completion Gate

Run both strict checks before changing any paper, slide, or report wording from
`pending human review` to `human-calibrated`:

```powershell
python '1号机代码\DATA_new\analysis\rq1_error_detection\summarize_rq1_human_adjudication.py' --require-complete
python '1号机代码\DATA_new\analysis\rq1_error_detection\validate_rq1_failure_audit_artifacts.py' --require-human-complete
```

Both commands must pass. If either command fails, keep the result marked as
pending and fix the reported row.

The current expected strict-check failure before annotation is:

```text
Human adjudication is incomplete: pending_rows=100
human adjudication is incomplete: pending_rows=100
```

## Report Language

Use this language before completion:

> We include a 400-row deterministic assisted audit as a reproducible preview.
> A 100-row human adjudication calibration pack has been prepared, but the
> human-calibrated estimate remains pending until all `human_*` labels pass the
> strict completion checks.

Use this language only after both strict checks pass:

> We report the human-calibrated estimate from the completed 100-row
> adjudication pack, with artifact validation confirming that all `human_*`
> labels are complete and internally consistent.

## Files Produced After Completion

After the strict checks pass, the final numbers should be read from:

- `human_adjudication_summary.json`
- `human_adjudication_summary.md`
- `artifact_validation_summary.json`
- `artifact_validation_summary.md`

The calibrated ADVTEST-vs-Random exclusive effect is under
`calibrated_estimates.exclusive_effect` in `human_adjudication_summary.json`.
