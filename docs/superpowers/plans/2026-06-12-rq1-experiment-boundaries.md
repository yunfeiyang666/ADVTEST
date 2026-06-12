# RQ1 Experiment Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate structural coverage baselines from external QA testing paradigms and enforce neutral data-sharing boundaries.

**Architecture:** Keep `fixed_budget_experiment.py` focused on controlled-space structural selection. Add a separate official-QA suite builder for external methods, with explicit provenance and leakage validation shared through a small protocol module.

**Tech Stack:** Python 3 standard library, `unittest`, existing RQ1 selectors and evaluator.

---

### Task 1: Add experiment protocol and leakage validation

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/experiment_protocol.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_experiment_protocol.py`

- [ ] Write tests asserting that external records reject ADVTEST-private fields and require provenance.
- [ ] Run the focused test and verify it fails because the protocol module does not exist.
- [ ] Implement layer definitions, provenance annotation, and leakage validation.
- [ ] Run the focused test and verify it passes.

### Task 2: Replace external pseudo-baselines in the structural runner

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/fixed_budget_experiment.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_fixed_budget_experiment.py`

- [ ] Write tests for deterministic random, template-balanced, object-balanced,
  L0-greedy, and L1-greedy streams.
- [ ] Write a test proving random does not use coverage-based early switching.
- [ ] Run the focused tests and verify the new cases fail.
- [ ] Implement the policies and method-specific switch behavior.
- [ ] Add provenance to every emitted structural question.
- [ ] Run the focused tests and verify they pass.

### Task 3: Build official NuScenes-QA suites independently

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/official_qa_experiment.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_official_qa_experiment.py`

- [ ] Write tests for indexing official QA by sample token.
- [ ] Write tests that QATest mutations preserve official source IDs and never
  inherit ADVTEST-private fields.
- [ ] Run the focused tests and verify they fail.
- [ ] Implement official QA loading, deterministic selection, and QATest mutation.
- [ ] Emit provenance and VLM call cost for every record.
- [ ] Run the focused tests and verify they pass.

### Task 4: Integrate QAAskeR's stateful MR2 boundary

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/qaasker_adapter.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_qaasker_adapter.py`

- [ ] Write a test showing a QAAskeR case requires a primary SUT answer before
  follow-up generation and costs two VLM calls.
- [ ] Run the test and verify it fails.
- [ ] Implement the state contract and run original Q2S/S2G modules in an
  isolated persistent process without inventing an offline selector.
- [ ] Run the test and verify it passes.

### Task 5: Verification and history

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/README.md`

- [ ] Run all RQ1 unit tests.
- [ ] Run small structural and official-QA smoke builds.
- [ ] Inspect generated provenance and confirm leakage checks pass.
- [ ] Update the README with the new experiment commands and interpretation.
- [ ] Review the diff for unrelated changes.
- [ ] Create a local Git commit containing only the protocol, implementation,
  tests, and documentation.
