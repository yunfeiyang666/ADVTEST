# RQ1 mPLUG Report Pack

This directory is generated from recorded RQ1 mPLUG summaries. It is intended as the paper-ready result pack for the equal-question-budget experiment.

## Headline

- ADVTEST finds +69 unique failures over Random (7.57%).
- Failed unique L2 increases by +1761 (64.58%), while input covered L2 increases by +1690 (59.97%).
- At 100 calls, ADVTEST exceeds all 3 Random seeds on unique failures and failed unique L2.

## Main Call1000 Table

| method_label | vlm_calls | wrong | failure_rate | unique_failures | unique_failures_per_100_calls | failed_unique_l2 | covered_l2 | unique_l2_per_question | visited_frames | gt_granularity |
|---|---|---|---|---|---|---|---|---|---|---|
| ADVTEST | 1000 | 981 | 0.981 | 981 | 98.100 | 4488 | 4508 | 4.508 | 20 | instance_or_relation |
| Random | 1000 | 912 | 0.912 | 912 | 91.200 | 2727 | 2818 | 2.818 | 20 | instance_or_relation |
| Official NuScenes-QA | 1000 | 650 | 0.650 | 650 | 65 | 0 | n/a | n/a | 67 | category_level_official |
| QATest-adapted | 1000 | 637 | 0.637 | 468 | 46.800 | 0 | n/a | n/a | 100 | category_level_official |

## ADVTEST vs Random Gains

| call_budget | unique_failure_delta | unique_failure_relative_gain | failed_unique_l2_delta | failed_unique_l2_relative_gain | input_covered_l2_delta | input_covered_l2_relative_gain |
|---|---|---|---|---|---|---|
| 20 | 7 | 0.583 | 15 | 0.938 | n/a | n/a |
| 100 | 6 | 0.070 | 67 | 0.396 | n/a | n/a |
| 1000 | 69 | 0.076 | 1761 | 0.646 | 1690 | 0.600 |

## Boundary Notes

- Cross-paradigm suites have different frame distributions and ground-truth granularities.
- Official QA and QATest-adapted do not expose structural L2 coverage and must not be used for coverage head-to-head claims.
- Correctness uses deterministic token-boundary lexical scoring rather than semantic judging.
- Structural L2 coverage and failed-L2 metrics are frame-qualified to avoid merging same-named objects across frames.

## Generated Files

- `report_pack.json`: complete structured payload.
- `table_main_call1000.csv`: main method comparison.
- `table_scaling.csv`: call20/call100/call1000 scaling trend.
- `table_adv_vs_random_gains.csv`: ADVTEST-vs-Random deltas.
- `table_random_variance.csv`: call100 random-seed robustness rows.
- `paper_claims.md`: claim-to-evidence mapping and caveats.

## Reproduction

Run from repository root:

```powershell
$codeRoot = (Get-ChildItem -Directory | Where-Object Name -Like '1*' | Select-Object -First 1).FullName
$script = Join-Path $codeRoot 'DATA_new\analysis\rq1_error_detection\build_rq1_report_pack.py'
python $script
```

Source artifacts:

- `experiments/rq1_mplug_smoke/call20_summary.json`
- `experiments/rq1_mplug_call100/call100_summary.json`
- `experiments/rq1_mplug_call1000/call1000_summary.json`
- `experiments/rq1_mplug_call1000/input_audit.json`
- `experiments/rq1_mplug_random_variance/random_variance_summary.json`
