# RQ2 Random Full-Coverage Runbook

## Protocol

For each frame, the official NuScenes-QA seed defines the initial coverage
`C0`. The immutable sampling pool is `G0 = G - C0`, where `G` is the complete
L2 universe. Every draw independently samples one gap from `G0` with
replacement, then samples one verified plan for that gap with replacement.

The selector cannot access coverage. Coverage is updated only after a question
has been realized, and is used only for reporting and the 100% L2 stop check.
Repeated gaps, plans, and question texts consume budget and are never redrawn.

## Focused Smoke

From `1号机代码/DATA_new/official_pipeline/code`:

```powershell
python run_gap_pipeline_v7.py `
  --plan generate `
  --artifact-root ../../outputs `
  --scene-id scene-1061 `
  --frame-id 21 `
  --seed 42 `
  --selection-policy random_full `
  --checkpoint-interval 2
```

An incomplete watchdog smoke can add `--max-draws 10`. Reaching that boundary
is an error and never produces a formal result.

## Formal All-Frame Run

```powershell
python run_random_full_coverage_experiment.py run `
  --seeds 42 43 44 `
  --checkpoint-interval 1000
```

The ordered frame pool comes from `outputs/all_frames_stats.csv` and includes
all frames with at least three filtered objects. Completed frame/seed runs are
skipped. Interrupted frames resume from their selector RNG and coverage
checkpoint.

Generate aggregate frame and S/M/L/All metrics only after the runs finish:

```powershell
python run_random_full_coverage_experiment.py report --seeds 42 43 44
```

## Outputs

Each frame writes under:

```text
outputs/<scene_frame>/random_full/seed_<seed>/
  checkpoint.json
  draws.jsonl
  unique_questions.jsonl
  summary.json
  manifest.json
```

`draws.jsonl` is the authoritative compact trace. `unique_questions.jsonl`
stores the first occurrence of each exact question text for inspection without
duplicating full records for every repeated draw.

The all-frame runner writes status and logs under
`scratch/rq2_random_full_coverage/`.
