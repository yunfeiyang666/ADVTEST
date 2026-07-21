# ADVTEST Agent Entry Rules

Read this file before doing anything. This repository contains long-running
RQ1/RQ2/RQ3 experiments; chat transcripts are not an authoritative source.

## Required first action

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\agent_preflight.ps1
```

Then read `EXPERIMENT_STATE.md`. Treat its `Last audited` timestamp and the
machine-readable status files named there as the current state. If they
conflict with an old report, transcript, or recap, report the conflict before
starting, modifying, or declaring an experiment complete.

## Non-negotiable working rules

- Do not read or summarize old Claude/Codex conversations unless specifically
  asked. They are historical context, not experiment state.
- Do not push, reset, checkout, revert, delete generated artifacts, or touch
  unrelated dirty/untracked files.
- Inspect `git status` before edits; use `apply_patch` for source edits.
- Commit each scoped code or documentation change separately. Do not commit
  model weights, mosaics, raw checkpoints, or `scratch/` outputs.
- A status JSON that says `running` is not proof a task is live: verify its
  matching process exists. A stale status must be reported as stale.
- Do not describe a partial run as complete. State the exact completed count,
  total count, run directory, and verification file.
- Never silently replace a real VLM with MOCK or change an experiment's frame
  pool, images, seed, question budget, coverage definition, or scoring rule.

## RQ2 Random boundary

For `random_fixed_budget`, selection is coverage-blind: it samples the fixed
initial gap pool with replacement, then a legal plan/template uniformly. It
must not read current coverage, prior draws, coverage gain, gap scores, or plan
quality while selecting. Repetitions are valid and must not be redrawn.

## Handoff protocol

At the end of any meaningful work:

1. Update `EXPERIMENT_STATE.md` only with verified facts and paths.
2. Record commands, commit hash, validation, active process/run id, and any
   blocker in the `Latest handoff` section.
3. Keep conclusions separate from planned work. Mark unverified claims as
   `UNVERIFIED`.
