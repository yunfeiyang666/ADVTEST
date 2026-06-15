# Strict mPLUG-Owl2 Call-20 Smoke

## Scope

This experiment validates the real mPLUG-Owl2 evaluation path for four RQ1
roles under an equal budget of 20 actual VLM calls per method:

- `advtest`: proposed method;
- `random`: internal ordering ablation;
- `official_qa`: neutral official reference;
- `qatest_adapted`: independent QATest comparison.

The run is a technical smoke, not the final statistical comparison. The four
20-question prefixes cover different numbers of frames, and Official QA uses
category-level answers while ADVTEST uses instance-level answers.

## Preflight

All suites passed the strict real-input preflight:

| Method | Questions | Calls | Frames | Missing GT | Missing mosaics |
|---|---:|---:|---:|---:|---:|
| `advtest` | 20 | 20 | 1 | 0 | 0 |
| `random` | 20 | 20 | 1 | 0 | 0 |
| `official_qa` | 20 | 20 | 2 | 0 | 0 |
| `qatest_adapted` | 20 | 20 | 18 | 0 | 0 |

The first preflight attempt incorrectly treated integer answer `0` as empty.
Commit `c8b14bd` added a regression test and corrected the validator. The
second attempt passed without changing any suite record.

## Recorded Run

- Run ID: `mplug-four-methods-call20`
- Generation/evaluation commit: `8206207600257d7b92d453aa3eb78ecab4ab5fd3`
- Branch: `codex/rq1-experiment-boundaries`
- Status: completed
- Exit code: 0
- Total wall time: 634.804 seconds
- GPU: NVIDIA GeForce RTX 3070 Laptop GPU, 8 GB
- Model source: local ModelScope `iic/mPLUG-Owl2`
- Quantization: 4-bit
- Real inference records: 80
- Mock fallback records: 0

Command:

```powershell
cd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection

python run_recorded_experiment.py `
  --run-id mplug-four-methods-call20 `
  --purpose "Strict real mPLUG-Owl2 four-method 20-call smoke after image preflight" `
  --run-root E:\Project\ADVTEST\scratch\rq1_mplug_smoke\runs `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_smoke\suites\advtest_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_smoke\suites\random_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_smoke\suites\official_qa_suite.jsonl `
  --input-file E:\Project\ADVTEST\scratch\rq1_mplug_smoke\suites\qatest_adapted_suite.jsonl `
  --parameter model=MPLUG `
  --parameter vlm_call_budget=20 `
  --parameter methods=advtest,random,official_qa,qatest_adapted `
  -- E:\Project\ADVTEST\.venv310\Scripts\python.exe run_suite_evaluation.py `
    --suite-dir E:\Project\ADVTEST\scratch\rq1_mplug_smoke\suites `
    --output-dir E:\Project\ADVTEST\scratch\rq1_mplug_smoke\runs\mplug-four-methods-call20\results `
    --outputs-root E:\Project\ADVTEST\1号机代码\DATA_new\outputs `
    --dataroot E:\Project\ADVTEST\1号机代码\DATA_new\data `
    --mode MPLUG `
    --methods advtest random official_qa qatest_adapted `
    --vlm-call-budget 20
```

## Results

| Method | Calls | Wrong | Failure rate | Unique failures | UF/100 calls | Calls/UF | Duplicate rate | Frames |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `advtest` | 20 | 19 | 0.950 | 19 | 95 | 1.053 | 0.000 | 1 |
| `official_qa` | 20 | 14 | 0.700 | 14 | 70 | 1.429 | 0.000 | 2 |
| `qatest_adapted` | 20 | 15 | 0.750 | 14 | 70 | 1.429 | 0.067 | 18 |
| `random` | 20 | 12 | 0.600 | 12 | 60 | 1.667 | 0.000 | 1 |

Average per-question inference time:

| Method | Average | Minimum | Maximum |
|---|---:|---:|---:|
| `advtest` | 5.427 s | 2.200 s | 11.914 s |
| `official_qa` | 7.146 s | 2.416 s | 15.777 s |
| `qatest_adapted` | 6.898 s | 3.310 s | 15.154 s |
| `random` | 8.210 s | 4.742 s | 13.910 s |

Every raw record has `mode=MPLUG`, a non-empty `raw_model_output`,
`error=null`, and a positive inference duration.

## Limitations

The checkpoint loader warned that several visual-abstractor q/k positional
embedding weights were newly initialized. The model completed real inference,
but the warning must remain visible when interpreting accuracy.

Correctness currently uses normalized answer containment. This is deterministic
and consistent across methods, but it is not a semantic judge.

The 20-call prefixes are not frame-balanced. ADVTEST and Random each remain in
one frame because their generator uses a 50-question per-frame cap, while
QATest-adapted draws from 18 frames. The smoke therefore validates execution
and accounting; it does not establish a final ranking.

## 100-Call Gate

The pipeline is technically eligible for a recorded 100-call run because all
four suites completed exactly 20 real calls with no fallback or missing image.
Before treating the 100-call result as a main comparison, the experiment must
retain the role labels and report the differing frame distribution and GT
granularity.

The next command is the same recorded invocation with freshly assembled
100-call suites, a new run ID, `--vlm-call-budget 100`, and a new output
directory. It is intentionally not executed in this stage.

Raw suites, mosaics, manifests, logs, and per-question outputs remain under
`scratch/rq1_mplug_smoke/` and are intentionally not committed.
