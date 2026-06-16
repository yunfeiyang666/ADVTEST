# mPLUG-Owl2 Call-1000 Input Gate

## Scope

This stage prepares the formal 1000-call-per-method RQ1 mPLUG evaluation
inputs. It does not run the 4000 real VLM inferences yet.

The frozen input policy is:

- use each method's emitted order;
- consume exactly 1000 actual VLM calls per method;
- keep ADVTEST and Random as the structurally comparable internal ablation;
- keep Official QA and QATest-adapted as cross-paradigm references with
  category-level NuScenes-QA ground truth;
- do not synthesize structural coverage fields for external methods.

## Input Suites

| Method | Calls | Frames | Max/frame | GT granularity | Coverage comparable |
|---|---:|---:|---:|---|---|
| `advtest` | 1000 | 20 | 50 | instance_or_relation | yes |
| `random` | 1000 | 20 | 50 | instance_or_relation | yes |
| `official_qa` | 1000 | 67 | 28 | category_level_official | no |
| `qatest_adapted` | 1000 | 100 | 29 | category_level_official | no |

The exact source/output hashes are in `assembly_manifest.json`.

Official QA initially had six same-frame normalized duplicate questions in the
first 1000 records. A recorded 1100-question Official source was generated, and
the final suite skips those six duplicates while continuing until it reaches
1000 valid calls. Details are in `official_qa_sanitize_manifest.json`.

## Structural Coverage

The ADVTEST versus Random input comparison is directly comparable because both
use the same 20 frames, 50-question frame cap, and structural coverage fields:

| Method | Covered L2 | Total L2 | Micro L2 | L2/Q |
|---|---:|---:|---:|---:|
| `advtest` | 4508 | 1028619 | 0.004383 | 4.508 |
| `random` | 2818 | 1028619 | 0.002740 | 2.818 |

ADVTEST covers 1690 more unique frame-qualified L2 items than Random, a 59.97%
relative micro-L2 gain and 1.690 additional L2 items per question.

Official QA and QATest-adapted intentionally do not expose structural L2
coverage. They must remain cross-paradigm references rather than coverage
head-to-head rows.

## Strict Preflight

All four suites passed strict mPLUG preflight:

| Method | Questions | Calls | Frames | Failure codes |
|---|---:|---:|---:|---|
| `advtest` | 1000 | 1000 | 20 | none |
| `random` | 1000 | 1000 | 20 | none |
| `official_qa` | 1000 | 1000 | 67 | none |
| `qatest_adapted` | 1000 | 1000 | 100 | none |

The machine-readable audit is in `preflight_summary.json`.

## Runbook

Expected runtime is about 8.3 hours on the RTX 3070 Laptop GPU, extrapolated
from the completed 400-call run at about 7.46 seconds per inference.

```powershell
cd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection

E:\Project\ADVTEST\.venv310\Scripts\python.exe run_recorded_experiment.py `
  --run-id mplug-four-methods-call1000 `
  --purpose "Strict real mPLUG-Owl2 four-method 1000-call evaluation" `
  --run-root E:\Project\ADVTEST\scratch\rq1_mplug_call1000\runs `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_call1000\suites\advtest_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_call1000\suites\random_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_call1000\suites\official_qa_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_call1000\suites\qatest_adapted_suite.jsonl `
  --parameter model=MPLUG `
  --parameter vlm_call_budget=1000 `
  --parameter methods=advtest,random,official_qa,qatest_adapted `
  -- E:\Project\ADVTEST\.venv310\Scripts\python.exe run_suite_evaluation.py `
    --suite-dir E:\Project\ADVTEST\scratch\rq1_mplug_call1000\suites `
    --output-dir E:\Project\ADVTEST\scratch\rq1_mplug_call1000\runs\mplug-four-methods-call1000\results `
    --outputs-root E:\Project\ADVTEST\1号机代码\DATA_new\outputs `
    --dataroot E:\Project\ADVTEST\1号机代码\DATA_new\data `
    --mode MPLUG `
    --methods advtest random official_qa qatest_adapted `
    --vlm-call-budget 1000
```

## Recorded mPLUG Run

The formal four-method run completed after the input gate:

- Run ID: `mplug-four-methods-call1000`
- Exit code: 0
- Duration: 32921.27 seconds, approximately 9.14 hours
- Real inference records: 4000
- Mock fallback records: 0
- Raw audit: no wrong mode, empty output, error, or nonpositive-duration record

All headline metrics use `token_boundary_v2_frame_qualified_l2` scoring over
the frozen raw outputs:

| Method | Role | Calls | Wrong | Independent failures | UF/100 | Duplicate rate | Failed unique L2 | Frames |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `advtest` | proposed | 1000 | 981 | 981 | 98.1 | 0.000 | 4488 | 20 |
| `random` | internal ablation | 1000 | 912 | 912 | 91.2 | 0.000 | 2727 | 20 |
| `official_qa` | neutral reference | 1000 | 650 | 650 | 65.0 | 0.000 | N/A | 67 |
| `qatest_adapted` | external comparison | 1000 | 637 | 468 | 46.8 | 0.265 | N/A | 100 |

The controlled internal ablation supports the coverage-guidance claim:

- ADVTEST covers 1690 more unique L2 items in its generated input than Random,
  a 59.97% relative micro-L2 gain.
- ADVTEST finds 69 more independent mPLUG failures than Random, a 7.57%
  relative gain.
- ADVTEST exposes 1761 more failed unique L2 items than Random, a 64.58%
  relative gain.

The cross-paradigm rows remain descriptive because Official QA and
QATest-adapted use category-level NuScenes-QA ground truth and do not carry
structural L2 coverage fields.

The machine-readable summaries are `call1000_summary.json` and
`call1000_rescored_v2.json`.
