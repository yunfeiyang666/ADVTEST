# ADVTEST Current Handoff

## Last audited

- Date: 2026-07-21, Asia/Shanghai
- Branch: `codex/rq1-experiment-boundaries`
- Current source of truth: this file plus `tools/agent_preflight.ps1` output,
  per-run status/summary/manifest files, and actual process state.

## Current goal

Prepare reproducible RQ1/RQ2 results for discussion while keeping the machine
usable. Do not infer completed work from an old chat recap.

## RQ2: budget-matched Random

- Purpose: compare Random against ADVTEST at the same **per-frame question
  count**. Each Random frame reads ADVTEST's `generated` value for that frame.
- Runner: `1号机代码/DATA_new/official_pipeline/code/run_random_budget_matched_experiment.py`
- Run directory: `scratch/rq2_random_budget_matched/formal-s42-v1`
- Run id: `rq2-random-budget-matched-s42-v1`; seed `42`; total `5767` frames.
- Last known status file recorded `completed=172`, `skipped=14`, `failed=0`.
  The status file said `running`, but no matching runner process was found at
  the audit. It is therefore **interrupted/resumable, not complete**.
- Frozen rule: Random samples the initial uncovered L2 gaps, legal plans and
  language templates with replacement, without reading accumulated coverage,
  draw history, coverage gains, gap scores, or plan quality. Repeats stay.
- Cache replay is allowed only after verifying the static gap set, plan IDs and
  candidate fingerprint. It is a speed optimization, never a selection rule.

## RQ1: MiniCPM evaluation

- Frozen formal manifest:
  `scratch/rq1_minicpm_shortanswer_eval_v2/rq1_full_frozen_manifest.json`
- The base short-answer evaluation was paused and is resumable. Do not restart
  it while a large Random job is active unless the user asks for that resource
  tradeoff.
- Legacy unconstrained MiniCPM outputs are not formal short-answer metrics and
  must not be mixed into final tables.

## RQ3: MiniCPM pilot fine-tuning

- Base model:
  `E:/hf_cache/modelscope_minicpm_core/openbmb/MiniCPM-o-2_6`
- Pilot adapter:
  `scratch/rq3_vlm_repair/runs/minicpm_o_2_6_pilot_formal_s42_finalepoch_v1/adapter`
- Training metadata reports about `0.99` epoch, not the intended three epochs.
  This is a pilot artifact, not a completed main experiment.
- A complete paired base-vs-adapter evaluation has not been verified.

## Known user-owned changes: do not touch

- `1号机代码/DATA_new/analysis/rq1_error_detection/evaluator.py`
- `1号机代码/DATA_new/analysis/rq1_error_detection/rq1_case_validity_analysis.md`
- `1号机代码/DATA_new/analysis/rq1_error_detection/run_minicpm_full_queue.py`
- Existing untracked environments, datasets, `scratch/`, `outputs/`, model
  artifacts, and historical suite results.

## Verified recent commits

- `132b512` - durable experiment handoff entrypoint
- `9dd6966` - web ChatGPT prompt coordinator handoff
- `c47423e` - replay Random coverage from verified cache
- `5642260` - share verified Random plan caches
- `6604e6c` - ADVTEST-budget-matched Random coverage runner

## Next minimal action

Run `powershell -ExecutionPolicy Bypass -File .\tools\agent_preflight.ps1`.
If the Random runner is absent, report its stale state before resuming it. Do
not invent a new RQ2 stopping rule or claim the partial run is final.
