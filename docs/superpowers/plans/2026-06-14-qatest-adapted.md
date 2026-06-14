# QATest-Adapted Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline, deterministic QATest adaptation with linguistic coverage feedback, integrate it with official NuScenes-QA generation, and audit a recorded 1000-question suite.

**Architecture:** `qatest_adapted.py` owns portable mutation operators, local Rouge-1, coarse POS/DTMC and n-gram metrics, and the iterative generator. `official_qa_experiment.py` remains the I/O boundary and provenance adapter. Tests exercise the generator independently before CLI integration.

**Tech Stack:** Python 3 standard library, `unittest`, existing experiment protocol and recorded-run tooling.

---

### Task 1: Portable linguistic metrics and operators

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/qatest_adapted.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_qatest_adapted.py`

- [x] Write failing tests for local Rouge-1, normalized duplicate detection,
  deterministic operators, POS transitions, n-grams, sentence probability, and
  grammar gain.
- [x] Run `python -m unittest test_qatest_adapted.py -v` and verify failure
  because the module does not exist.
- [x] Implement only the metric and operator functions required by the tests.
- [x] Run focused tests and verify all pass.
- [x] Commit as `feat(rq1): add portable QATest language metrics`.

### Task 2: Iterative QATest generator

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/qatest_adapted.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_qatest_adapted.py`

- [x] Write failing tests for weighted deterministic seed selection, ten-attempt
  quality filtering, duplicate rejection, feedback seed insertion, provenance
  source preservation, and strict generation-budget termination.
- [x] Run focused tests and verify they fail for missing generator behavior.
- [x] Implement `QATestSeed`, `QATestCoverageModel`, `QATestGenerator`, and a
  generation-result object with records and statistics.
- [x] Run focused and complete RQ1 tests.
- [x] Commit as `feat(rq1): implement iterative QATest adaptation`.

### Task 3: Official-QA integration

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/official_qa_experiment.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_official_qa_experiment.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/README.md`

- [x] Write failing tests requiring `qatest_style`, `qatest_adapted`, and the
  compatibility alias `qatest`.
- [x] Require alias output to use `experiment_method=qatest_style`.
- [x] Require adapted output to preserve official source IDs, use
  `qatest_adapted_portable`, and contain no ADVTEST-private fields.
- [x] Implement the method dispatch and write an adapted statistics JSON file.
- [x] Run all RQ1 tests and compile changed scripts.
- [x] Commit as `feat(rq1): integrate QATest-adapted baseline`.

### Task 4: Recorded 1000-question audit

**Files:**
- Create: `experiments/rq1_qatest_adapted/README.md`
- Create: `experiments/rq1_qatest_adapted/run_index.json`
- Create: `experiments/rq1_qatest_adapted/suite_audit.json`

- [x] Generate `qatest_style` and `qatest_adapted` from the fixed 100-frame
  cache with `generation_budget=1000` through `run_recorded_experiment.py`.
- [x] Verify both suites contain 1000 unique normalized questions.
- [x] Verify source IDs, sample tokens, provenance, answer preservation, and
  absence of ADVTEST-private fields.
- [x] Compare elapsed time, attempted candidates, operator distribution, source
  diversity, and duplicate rejection.
- [x] Run complete regression and `git diff --check`.
- [x] Commit as `exp(rq1): audit QATest-adapted generation`.
