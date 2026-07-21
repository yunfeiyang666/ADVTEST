# ADVTEST Experiment State

This is the small, durable handoff file for a new agent. It deliberately does
not try to summarize all prior discussions. Verify paths and process state
before acting.

## Last audited

- Timestamp: 2026-07-21 Asia/Shanghai
- Branch: `codex/rq1-experiment-boundaries`
- Latest relevant commits:
  - `c47423e` - replay Random coverage from a verified cache
  - `5642260` - share verified Random plan caches
  - `6604e6c` - add ADVTEST-budget-matched Random coverage runner
  - `44ca4c0` - cache MiniCPM vision state and Random draw footprints

## Current live-state warning

The Random status file below says `running`, but no matching runner process was
found during this audit. Treat it as a stopped/interrupted, resumable run until
`tools/agent_preflight.ps1` proves otherwise.

## Active priority: RQ2 budget-matched Random

Purpose: compare coverage at the same per-frame question count as ADVTEST.

- Run directory:
  `scratch/rq2_random_budget_matched/formal-s42-v1`
- Status:
  `scratch/rq2_random_budget_matched/formal-s42-v1/status.json`
- Run id: `rq2-random-budget-matched-s42-v1`
- Seed: `42`
- Status last reported: `completed=172`, `skipped=14`, `failed=0`,
  `total=5767`; this must be rechecked before resuming.
- Runner:
  `1号机代码/DATA_new/official_pipeline/code/run_random_budget_matched_experiment.py`
- Pipeline:
  `1号机代码/DATA_new/official_pipeline/code/run_gap_pipeline_v7.py`

### Frozen scientific setup

For each frame, read ADVTEST's existing `reports/*_summary.json` field
`generated` as Random's exact question budget. Both methods use the same
frame, NuScenes-QA seed-derived initial coverage, labelled six-camera mosaic,
L2 universe, and legality checks.

Random uses a static initial uncovered-gap pool. For every draw it samples a
gap, plan and language template with replacement without reading the evolving
coverage accumulator. Duplicates are retained. Coverage is only accumulated
after selection for reporting.

### Cache behavior

`c47423e` can replay a frame from a prior verified plan cache only after
checking its full static gap set, plan IDs, and candidate fingerprint. A cache
hit is an implementation optimization, not a selection-policy change. A cache
miss must follow the original complete planning/validation path.

## RQ1 state

- mPLUG RQ1 result artifacts and case analyses already exist. Do not regenerate
  them merely because an old recap gives a different number; inspect the named
  suite reports first.
- MiniCPM frozen evaluation manifest:
  `scratch/rq1_minicpm_shortanswer_eval_v2/rq1_full_frozen_manifest.json`
- MiniCPM base evaluation was intentionally paused. It is resumable; do not
  restart it while a large Random job is running unless the user requests that
  resource tradeoff.
- Existing MiniCPM outputs include legacy unconstrained results. They are not
  formal short-answer results and must not be mixed into reported metrics.

## RQ3 MiniCPM pilot state

- Base model:
  `E:/hf_cache/modelscope_minicpm_core/openbmb/MiniCPM-o-2_6`
- Pilot adapter:
  `scratch/rq3_vlm_repair/runs/minicpm_o_2_6_pilot_formal_s42_finalepoch_v1/adapter`
- The artifact exists, but training metadata reports about `0.99` epoch, not
  the planned three epochs. It is a pilot artifact, not a completed main study.
- No complete paired base-vs-adapter formal evaluation has been verified.

## Known user-owned changes: leave untouched

- `1号机代码/DATA_new/analysis/rq1_error_detection/rq1_case_validity_analysis.md`
- `1号机代码/DATA_new/analysis/rq1_error_detection/run_minicpm_full_queue.py`
- Existing untracked environments, datasets, `scratch/`, `outputs/`, model
  artifacts, and historical suite results.

## Latest handoff

- The old task reporter mixed distinct RQ2 frame pools and treated partial
  work as final. Do not use its generated recap as evidence.
- Next agent action: run preflight; if the RQ2 runner is absent, report the
  stale status and ask/act according to the user's latest instruction before
  resuming. Do not invent a new RQ2 stopping rule.
