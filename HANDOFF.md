# ADVTEST Current Handoff

## Last audited

- Date: 2026-07-22 08:49 Asia/Shanghai
- Branch: `codex/rq1-experiment-boundaries`
- HEAD: `41190cb` — feat(rq1): add seeded strict and choice interfaces
- Current source of truth: this file plus verified process/status state.

## RQ2: budget-matched Random — ALL WORKERS STOPPED

- Run id: `rq2-random-budget-matched-s42-v1`; seed 42; total 5767 frames.
- The parallel workers (4 × ~855 frames) were launched, ran to completion or failure, then stopped. **No processes are running.**
- Worker results:
  - Worker 00 (855 frames): **242 completed, 613 failed**
  - Worker 01 (855 frames): **58 completed, 797 failed**
  - Worker 02 (855 frames): **837 completed, 18 failed** ← best performer
  - Worker 03 (853 frames): **28 completed, 32 failed** ← stale "running"
- **Total completed across all workers: ~1165 frames.** (remaining failed or unprocessed)
- Worker 03 status is stale (`"running"` with no process).
- `build_progress.json` from the initial single-process attempt: 178 done, 43 failed (baseline before parallel split).
- The `status.json` at root (`14 completed / 207 skipped / 22 failed`) is **outdated / misleading** — the parallel workers' individual status files are the real source.
- Frozen rule remains: Random samples the initial uncovered L2 gaps, legal plans and language templates with replacement, without reading accumulated coverage, draw history, coverage gains, gap scores, or plan quality.

## RQ1: MiniCPM evaluation

- Frozen formal manifest:
  `scratch/rq1_minicpm_shortanswer_eval_v2/rq1_full_frozen_manifest.json`
- The base short-answer evaluation was paused and is resumable. Do not restart it while a large Random job is active.
- Legacy unconstrained MiniCPM outputs are not formal short-answer metrics.

## RQ3: MiniCPM pilot fine-tuning

- Base model: `E:/hf_cache/modelscope_minicpm_core/openbmb/MiniCPM-o-2_6`
- Pilot adapter: `scratch/rq3_vlm_repair/runs/minicpm_o_2_6_pilot_formal_s42_finalepoch_v1/adapter`
- Training metadata reports ~0.99 epoch (not the intended 3). This is a pilot artifact.
- A complete paired base-vs-adapter evaluation has not been verified.

## Known user-owned changes: do not touch

- `1号机代码/DATA_new/analysis/rq1_error_detection/evaluator.py`
- `1号机代码/DATA_new/analysis/rq1_error_detection/rq1_case_validity_analysis.md`
- `1号机代码/DATA_new/analysis/rq1_error_detection/run_minicpm_full_queue.py`
- Existing untracked environments, datasets, `scratch/`, `outputs/`, model artifacts, and historical suite results.

## Next steps

- RQ2: decide whether to re-run failed frames or accept the partial results (~1165 of 5767).
- RQ1: resume MiniCPM short-answer evaluation, or analyze existing results.
- RQ3: complete the paired base-vs-adapter evaluation.
