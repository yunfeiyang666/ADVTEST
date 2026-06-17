# RQ1 Evening Report Source Index

Date: 2026-06-17

This file maps the evening report claims to the exact artifacts that support
them. It is meant for quick backtracking during discussion: if someone asks
"where did this number come from?", check this file first.

## Main Report

- Presentation draft:
  `experiments/rq1_report_pack/rq1_evening_report_2026-06-17.md`
- Slide outline:
  `experiments/rq1_report_pack/rq1_fault_detection_slide_outline_2026-06-17.md`
- Longer briefing:
  `experiments/rq1_report_pack/rq1_fault_detection_briefing_2026-06-17.md`

## Method Boundaries

| Claim | Source artifact |
|---|---|
| ADVTEST vs Random is the structurally comparable internal ablation. | `experiments/rq1_mplug_call1000/input_audit.json`; `experiments/rq1_mplug_call1000/README.md` |
| Official-QA and QATest-adapted are cross-paradigm references, not structural L2 head-to-head rows. | `experiments/rq1_mplug_call1000/input_audit.json`; `experiments/rq1_mplug_call1000/call1000_summary.json` |
| QAAskeR is excluded from the main 1000-call table because a complete primary/follow-up pair costs at least two VLM calls. | `1号机代码/DATA_new/analysis/rq1_error_detection/README.md`; `1号机代码/DATA_new/analysis/rq1_error_detection/qaasker_adapter.py`; `1号机代码/DATA_new/analysis/rq1_error_detection/run_qaasker_evaluation.py` |
| QATest-adapted uses official NuScenes-QA seeds and does not read ADVTEST coverage fields. | `experiments/rq1_qatest_adapted/suite_audit.json`; `experiments/rq1_qatest_adapted/README.md`; `1号机代码/DATA_new/analysis/rq1_error_detection/qatest_adapted.py` |

## Budget Claims

| Claim | Value | Source artifact |
|---|---:|---|
| Main evaluation budget per method | 1000 real VLM calls | `experiments/rq1_mplug_call1000/call1000_summary.json` |
| Total real inference records | 4000 | `experiments/rq1_mplug_call1000/call1000_summary.json` |
| Mock fallback records | 0 | `experiments/rq1_mplug_call1000/call1000_summary.json` |
| Run duration | 32921.27 seconds, about 9.14 hours | `experiments/rq1_mplug_call1000/call1000_summary.json`; `experiments/rq1_mplug_call1000/README.md` |
| Scoring version | `token_boundary_v2_frame_qualified_l2` | `experiments/rq1_mplug_call1000/call1000_summary.json` |

## Input Gate Claims

| Method | Calls | Frames | Max/frame | GT granularity | Coverage comparable | Source |
|---|---:|---:|---:|---|---:|---|
| ADVTEST | 1000 | 20 | 50 | instance_or_relation | yes | `experiments/rq1_mplug_call1000/input_audit.json` |
| Random | 1000 | 20 | 50 | instance_or_relation | yes | `experiments/rq1_mplug_call1000/input_audit.json` |
| Official-QA | 1000 | 67 | 28 | category_level_official | no | `experiments/rq1_mplug_call1000/input_audit.json` |
| QATest-adapted | 1000 | 100 | 29 | category_level_official | no | `experiments/rq1_mplug_call1000/input_audit.json` |

The structural input comparison is:

| Method | Covered L2 | Total L2 | Micro L2 | L2/question | Source |
|---|---:|---:|---:|---:|---|
| ADVTEST | 4508 | 1028619 | 0.004383 | 4.508 | `experiments/rq1_mplug_call1000/input_audit.json` |
| Random | 2818 | 1028619 | 0.002740 | 2.818 | `experiments/rq1_mplug_call1000/input_audit.json` |

Derived input coverage gain:

- ADVTEST minus Random covered L2: `1690`
- Relative micro-L2 gain: `59.97%`
- Source: `experiments/rq1_mplug_call1000/input_audit.json`

## Main mPLUG-Owl2 Call-1000 Results

Source:

- `experiments/rq1_mplug_call1000/call1000_summary.json`
- `experiments/rq1_mplug_call1000/call1000_rescored_v2.json`
- `experiments/rq1_mplug_call1000/README.md`

| Method | Calls | Wrong | Independent failures | UF/100 | Duplicate rate | Failed unique L2 | Frames |
|---|---:|---:|---:|---:|---:|---:|---:|
| ADVTEST | 1000 | 981 | 981 | 98.1 | 0.000 | 4488 | 20 |
| Random | 1000 | 912 | 912 | 91.2 | 0.000 | 2727 | 20 |
| Official-QA | 1000 | 650 | 650 | 65.0 | 0.000 | N/A | 67 |
| QATest-adapted | 1000 | 637 | 468 | 46.8 | 0.265 | N/A | 100 |

Derived ADVTEST vs Random gains:

| Metric | Gain | Relative gain | Source |
|---|---:|---:|---|
| Input covered L2 | +1690 | +59.97% | `input_audit.json`; `call1000_summary.json` |
| Independent failures | +69 | +7.57% | `call1000_summary.json` |
| Failed unique L2 | +1761 | +64.58% | `call1000_summary.json` |

Use this wording:

> ADVTEST has a modest raw independent-failure gain and a much larger
> failed-structural-coverage gain over Random.

Do not say:

> Official-QA or QATest-adapted loses on structural L2 coverage.

They do not carry structural L2 footprints by design.

## Random Seed Robustness

Source:

- `experiments/rq1_mplug_random_variance/random_variance_summary.json`
- `experiments/rq1_mplug_random_variance/README.md`

| Method | Seed | Calls | Independent failures | Failed unique L2 |
|---|---:|---:|---:|---:|
| ADVTEST | fixed | 100 | 92 | 236 |
| Random | 42 | 100 | 86 | 169 |
| Random | 43 | 100 | 88 | 180 |
| Random | 44 | 100 | 90 | 183 |

Derived summary:

- Random independent-failure mean: `88.00`
- Random independent-failure population std: `1.63`
- Random failed unique L2 mean: `177.33`
- Random failed unique L2 population std: `6.02`
- ADVTEST independent-failure gain over Random mean: `+4.00`, or `+4.55%`
- ADVTEST failed unique L2 gain over Random mean: `+58.67`, or `+33.08%`
- ADVTEST exceeds all three Random seeds on both metrics.

## QATest-adapted Generation Audit

Source:

- `experiments/rq1_qatest_adapted/suite_audit.json`
- `experiments/rq1_qatest_adapted/README.md`

| Method | Questions | Unique normalized questions | Source question count | Frames | Answer mismatches | Boundary violations |
|---|---:|---:|---:|---:|---:|---:|
| qatest_style | 1000 | 1000 | 1000 | 99 | 0 | 0 |
| qatest_adapted | 1000 | 1000 | 723 | 100 | 0 | 0 |

Use this wording:

> QATest-adapted is the reproducible external comparison. It preserves the
> core QATest-style mutation/filtering idea while using only official
> NuScenes-QA seeds and avoiding non-reproducible or credential-dependent
> operators.

Do not say:

> We exactly reproduce the original QATest implementation.

## Failure Audit

### 48-row manual sanity audit

Source:

- `experiments/rq1_failure_audit/manual_review_summary.json`
- `experiments/rq1_failure_audit/manual_review_summary.md`

| Bucket | Rows | Valid yes | Valid rate |
|---|---:|---:|---:|
| advtest_only_l2 | 12 | 8 | 66.7% |
| random_only_l2 | 12 | 9 | 75.0% |
| shared_l2_advtest | 12 | 8 | 66.7% |
| shared_l2_random | 12 | 8 | 66.7% |

Overall:

- Valid visual/structural failures: `33/48`, or `68.8%`
- Boundary cases: `15/48`

### 400-row deterministic assisted audit

Source:

- `experiments/rq1_failure_audit_large/large_assisted_review_summary.json`
- `experiments/rq1_failure_audit_large/large_assisted_review_summary.md`
- `experiments/rq1_failure_audit_large/README.md`

| Bucket | Sample rows | Valid yes | Uncertain | Valid rate | Estimated valid total |
|---|---:|---:|---:|---:|---:|
| advtest_only_l2 | 100 | 70 | 6 | 70.0% | 2149.0 |
| random_only_l2 | 100 | 87 | 3 | 87.0% | 1138.8 |
| shared_l2_advtest | 100 | 77 | 8 | 77.0% | 1091.9 |
| shared_l2_random | 100 | 77 | 8 | 77.0% | 1091.9 |

Derived assisted-audit effect:

- ADVTEST-only estimated valid total: `2149.0`
- Random-only estimated valid total: `1138.8`
- Difference: `+1010.2`
- Conservative Wilson lower-minus-upper: `+647.3`

Use this wording:

> The assisted audit supports the direction of the ADVTEST advantage, but the
> final human-calibrated estimate is still pending.

Do not say:

> The 400-row audit is final human adjudication.

## Human Adjudication Status

Source:

- `experiments/rq1_failure_audit_large/human_adjudication_pack.csv`
- `experiments/rq1_failure_audit_large/human_adjudication_summary.json`
- `experiments/rq1_failure_audit_large/artifact_validation_summary.json`
- `experiments/rq1_failure_audit_large/human_adjudication_runbook_2026-06-17.md`

Current status:

- Human adjudication rows: `100`
- Reviewed rows: `0`
- Pending rows: `100`
- Assisted labels in the pack: `yes=43`, `no=32`, `uncertain=25`
- Calibrated estimates: `not_available_until_human_rows_are_reviewed`

Strict completion commands:

```powershell
python '1号机代码\DATA_new\analysis\rq1_error_detection\summarize_rq1_human_adjudication.py' --require-complete
python '1号机代码\DATA_new\analysis\rq1_error_detection\validate_rq1_failure_audit_artifacts.py' --require-human-complete
```

Current expected strict-check failure:

```text
Human adjudication is incomplete: pending_rows=100
human adjudication is incomplete: pending_rows=100
```

## Verification Commands

Run these from `E:\Project\ADVTEST`.

Normal artifact check:

```powershell
python '1号机代码\DATA_new\analysis\rq1_error_detection\validate_rq1_failure_audit_artifacts.py'
```

Expected current result:

```text
[rq1-artifact-validation] status=ok large_rows=400 human_rows=100 human_pending=100
```

Full RQ1 unit tests:

```powershell
cd '1号机代码\DATA_new\analysis\rq1_error_detection'
python -m unittest discover -p "test_*.py" -v
```

Last known result after the strict human gate was added:

```text
Ran 128 tests
OK
```

## One-Screen Claim Boundary

Safe claims:

- ADVTEST vs Random is the fair internal comparison.
- ADVTEST improves independent failures by `+69`, or `+7.57%`, at 1000 calls.
- ADVTEST improves failed unique L2 by `+1761`, or `+64.58%`, at 1000 calls.
- QATest-adapted and Official-QA are external/cross-paradigm references.
- The 400-row assisted audit supports the direction of the advantage.
- Human-calibrated audit results are pending.

Unsafe claims:

- QATest-adapted is an exact reproduction of original QATest.
- Official-QA or QATest-adapted is worse on structural L2 coverage.
- QAAskeR has already been fairly compared in the 1000-call main table.
- The 400-row assisted audit is final human adjudication.
- The 100-row human pack has been reviewed.
