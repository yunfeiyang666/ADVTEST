# RQ1 QATest-Adapted Generation Audit

## Goal

Compare the legacy `qatest_style` generator with the portable iterative
`qatest_adapted` baseline under the same fixed conditions:

- official NuScenes-QA seeds only;
- the fixed 100-frame cache;
- `generation_budget=1000`;
- `seed=42`;
- no real VLM calls during generation.

The input frame cache SHA-256 is:

```text
6a76177b6d3bbb9c52159933680527caf03862dd78b3f237176dda54e0a0c797
```

The formal runs used commit `980817f3fe4f78c46ce5e731e3d4678000d0c105`
on branch `codex/rq1-experiment-boundaries`.

## Commands

Run from:

```powershell
cd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection
```

Combined generation:

```powershell
python run_recorded_experiment.py `
  --run-id qatest-style-vs-adapted-1000 `
  --purpose "100-frame 1000-question QATest-style versus QATest-adapted generation audit" `
  --run-root E:\Project\ADVTEST\scratch\rq1_qatest_adapted\runs `
  --input-file E:\Project\ADVTEST\1号机代码\DATA_new\analysis\data_cache\rq1_100_eval_frames.json `
  --parameter generation_budget=1000 `
  --parameter seed=42 `
  --parameter frame_pool_size=100 `
  -- python official_qa_experiment.py `
    --methods qatest_style qatest_adapted `
    --generation-budget 1000 `
    --frame-pool-size 100 `
    --seed 42 `
    --output-dir E:\Project\ADVTEST\scratch\rq1_qatest_adapted\runs\qatest-style-vs-adapted-1000\results
```

Audit:

```powershell
python qatest_suite_audit.py `
  --suite E:\Project\ADVTEST\scratch\rq1_qatest_adapted\runs\qatest-style-vs-adapted-1000\results\qatest_style_suite.jsonl `
  --suite E:\Project\ADVTEST\scratch\rq1_qatest_adapted\runs\qatest-style-vs-adapted-1000\results\qatest_adapted_suite.jsonl `
  --output E:\Project\ADVTEST\experiments\rq1_qatest_adapted\suite_audit.json
```

Separate timing runs used the same arguments with one method per invocation.
Their run IDs are listed in `run_index.json`.

## Integrity Results

| Method | Questions | Unique | Official sources | Frames | Answer mismatches | Boundary violations |
|---|---:|---:|---:|---:|---:|---:|
| `qatest_style` | 1000 | 1000 | 1000 | 99 | 0 | 0 |
| `qatest_adapted` | 1000 | 1000 | 723 | 100 | 0 | 0 |

Both suites preserve official source IDs, source sample tokens, and official
answers. Neither suite contains ADVTEST-private coverage fields.

## Generation Behavior

`qatest_style` accepted all 1000 questions from its first seed pass. Every
question used `double_question_mark`, so the method is diverse by source but
degenerate by mutation operator.

`qatest_adapted` produced:

| Metric | Value |
|---|---:|
| Accepted questions | 1000 |
| Attempted candidates | 1478 |
| Duplicate rejections | 478 |
| Quality rejections | 0 |
| Feedback insertions | 357 |
| Iterations | 200 |

Accepted operator distribution:

| Operator | Accepted |
|---|---:|
| `keyboard_substitution` | 234 |
| `spelling_deletion` | 232 |
| `ocr_substitution` | 201 |
| `double_question_mark` | 188 |
| `synonym_replacement` | 120 |
| `wh_contraction` | 25 |

`adverbial_preposition` was attempted 194 times but produced no accepted
candidate. The portable mutations were mild enough that the Rouge threshold
rejected no candidates; duplicate filtering, not quality filtering, was the
active rejection mechanism in this run.

## Timing

| Method | Recorded duration |
|---|---:|
| `qatest_style` | 1.362 s |
| `qatest_adapted` | 18.652 s |

The adapted method is about 13.7 times slower in offline generation because it
scores linguistic coverage, retries candidates, and updates its seed pool.
This cost does not consume the later VLM-call budget.

## Smoke History

The first 20-question smoke run, `qatest-adapted-smoke20`, exposed misleading
operator attribution: inapplicable synonym mutations fell back to another
mutation while retaining the synonym label. Commit `980817f` removed that
fallback. `qatest-adapted-smoke20-retry1` then passed with correct attribution.

## Decision

Use `qatest_adapted` as the primary QATest comparison. Keep `qatest_style` only
as a legacy ablation because its 1000-question result is effectively a single
punctuation mutation over 1000 official seeds.

Before the final paper run, treat the inactive Rouge rejection and the zero
acceptance of `adverbial_preposition` as sensitivity items rather than silently
claiming all original QATest mechanisms are equally active.

Raw manifests, logs, and generated suites are stored under
`scratch/rq1_qatest_adapted/runs/` and are intentionally not committed.
