# Fixed-Budget RQ1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an offline 1,000-question, cross-frame coverage comparison for four RQ1 methods.

**Architecture:** Add a focused runner that loads the shared frame pool and
existing question artifacts, creates one ordered stream per method and frame,
applies the approved adaptive switch policy, and aggregates coverage against a
shared global universe. Keep VLM evaluation separate by exporting frozen JSONL
suites.

**Tech Stack:** Python 3.10 standard library, existing RQ1 selector modules,
`unittest`.

---

### Task 1: Switching Policy

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/fixed_budget_experiment.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_fixed_budget_experiment.py`

- [ ] Write failing tests for full coverage, ten-question plateau, relative
  gain decay, candidate exhaustion, and the 100-question hard cap.
- [ ] Run:
  `.venv310/Scripts/python.exe -m unittest 1号机代码/DATA_new/analysis/rq1_error_detection/test_fixed_budget_experiment.py -v`
  and confirm failures are caused by missing policy functions.
- [ ] Implement `SwitchPolicy` and `choose_switch_reason`.
- [ ] Re-run the focused tests and confirm all pass.

### Task 2: Coverage Accounting

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/fixed_budget_experiment.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_fixed_budget_experiment.py`

- [ ] Add failing tests showing that L2 footprints are deduplicated per frame
  and that unvisited frames remain in the common micro/macro denominator.
- [ ] Implement per-frame sets and global micro/macro aggregation.
- [ ] Re-run the focused test module.

### Task 3: Method Streams and Export

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/fixed_budget_experiment.py`

- [ ] Load 30 frames from `rq1_100_eval_frames.json`.
- [ ] Build deterministic streams for ADVTEST, Random, QATest, and QAAskeR.
- [ ] Consume each stream under the global and per-frame budgets.
- [ ] Export each frozen suite plus summary, curves, and switch diagnostics.

### Task 4: Trial Verification

**Files:**
- Create under:
  `1号机代码/DATA_new/analysis/fixed_budget_results/`

- [ ] Run the experiment with `--budget 1000 --frame-pool-size 30 --seed 42`.
- [ ] Verify each non-exhausted suite contains exactly 1,000 records.
- [ ] Verify all methods use the same frame list and denominator.
- [ ] Verify cumulative coverage is monotonic and bounded by one.
- [ ] Summarize the first-run comparison and any threshold sensitivity risks.

