# RQ1 Formal Exploration Design

## Goal

Turn the current RQ1 prototype into a reproducible formal experiment while
preserving a complete record of assumptions, commands, outputs, verification,
and Git history.

## Scope

This exploration proceeds in three ordered stages:

1. establish repository-local experiment tracking;
2. study 100-frame generation capacity and structural-coverage sensitivity;
3. use the resulting evidence to design baseline-fidelity and real-VLM runs.

The first implementation cycle covers stages 1 and 2 only. It does not start a
long real-VLM evaluation.

## Reproducibility Contract

Every experiment run receives a unique run ID and a dedicated output directory.
Its repository-tracked record contains:

- purpose and hypothesis;
- exact command;
- Git commit and branch;
- input frame cache and its content hash;
- method, seed, generation budget, and per-frame cap;
- start time, end time, duration, and exit status;
- paths to raw outputs;
- summarized metrics and observations;
- known limitations and the next decision.

Large suites, raw logs, mosaics, and generated JSONL files remain outside Git.
Small manifests, summaries, and Markdown operation notes are tracked.

## Git Strategy

Work remains on `codex/rq1-experiment-boundaries`.

Each meaningful phase gets a separate local commit:

1. experiment tracking and manifest tooling;
2. 100-frame structural sensitivity runner;
3. generated evidence summary and protocol decision.

Commits contain only code, tests, configuration, and concise reproducibility
records. Existing model environments, cloned baselines, cached datasets, and
unrelated result directories are not staged. No remote push occurs without
explicit approval.

## Stage 1: Experiment Tracking

Add a repository-local RQ1 experiment ledger and a small runner that records
commands and metadata before and after execution.

The runner must:

- write the manifest before launching the subprocess;
- capture stdout and stderr in the run directory;
- update duration and exit status even when the command fails;
- refuse to overwrite an existing run ID unless explicitly requested;
- avoid recording credentials or environment secrets.

The ledger links each run ID to its manifest, summary, status, and associated
Git commit.

## Stage 2: Structural Sensitivity

Use the fixed 100-frame cache in deterministic order.

Common settings:

- generation budget: 1000 questions per method;
- frame pool: 100 cached frames;
- per-frame caps: 50 and 100;
- deterministic methods: one run each;
- stochastic `random`: seeds 42, 43, and 44.

The experiment reports:

- L0, L1, and L2 micro coverage;
- L0, L1, and L2 macro coverage;
- normalized coverage AUC;
- unique L2 items per generated question;
- generated suite size;
- visited-frame count;
- frame-switch reason distribution;
- mean, standard deviation, minimum, and maximum for Random across seeds.

Official NuScenes-QA and QATest capacity are measured separately on the same
100-frame order with a requested generation budget of 1000. Official QA is not
repeated to fill the budget; actual capacity is reported explicitly.

## Interpretation Rules

Structural methods may be ranked by coverage only because they share the same
candidate space. Official QA, QATest, and QAAskeR are not ranked by ADVTEST
coverage in this stage.

The selected per-frame cap must be based on both:

- coverage or AUC improvement from cap 50 to cap 100;
- whether the smaller cap forces excessive frame switching or prevents the
  1000-question budget from being filled.

If cap 100 provides negligible benefit, cap 50 is preferred for efficiency.
The threshold for "negligible" is an absolute Micro-L2 improvement below 0.005
and a normalized AUC improvement below 0.005 for ADVTEST.

## Verification

Before each commit:

- new behavior is developed test-first;
- focused tests pass;
- the complete RQ1 unit-test suite passes;
- `git diff --check` passes;
- staged files are reviewed against the intended phase;
- generated manifests are checked for paths, hashes, status, and duration.

Stage 2 is complete only when all requested runs finish successfully and a
tracked summary can be regenerated from their manifests and result files.

## Deferred Decisions

The following decisions are deliberately deferred until structural evidence is
available:

- whether to run the original QATest environment or label the current adapter
  as a QATest-style baseline;
- the formal common VLM-call budget;
- whether QAAskeR receives a full 1000-call capacity run;
- whether MiniCPM is added as a second tested VLM.
