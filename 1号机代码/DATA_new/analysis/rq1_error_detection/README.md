# RQ1 Error Detection Experiments

This directory contains the RQ1 structural-coverage experiments, independent
official-QA baselines, VLM evaluation, and SFT export utilities.

## Experiment Boundary

The experiment is split into separate layers. Do not combine their rankings.

### Structural Coverage Layer

All methods receive the same frame order and complete programmatically
generatable question space:

- `advtest`: existing coverage-prioritized order with adaptive frame switching.
- `random`: complete random sampling with no gap or coverage feedback.
- `template_balanced`: balanced sampling across template families.
- `object_balanced`: balanced sampling across involved objects.
- `greedy_l0`: object-coverage-only greedy baseline.
- `greedy_l1`: one-hop-relation-only greedy baseline.

Run:

```powershell
python 1号机代码/DATA_new/analysis/rq1_error_detection/fixed_budget_experiment.py `
  --generation-budget 1000 `
  --frame-pool-size 100 `
  --max-questions 100 `
  --output-dir 1号机代码/DATA_new/analysis/fixed_budget_results/v2_structural
```

Only this layer compares L0/L1/L2 coverage curves directly.

### Cross-Paradigm Layer

Official QA and QATest use only official NuScenes-QA records matched by
`sample_token`. They cannot read ADVTEST-generated questions, uncovered gaps,
coverage footprints, or ADVTEST scores.

Run:

```powershell
python 1号机代码/DATA_new/analysis/rq1_error_detection/official_qa_experiment.py `
  --methods official_qa qatest `
  --generation-budget 1000 `
  --frame-pool-size 100 `
  --output-dir 1号机代码/DATA_new/analysis/official_qa_results/v1
```

`qatest` currently uses the dependency-light `qatest_local_adapter`, derived
from QATest-style textual transformations. It is intentionally not labeled as
an exact run of the original Python 3.6 environment.

QAAskeR is exposed through `qaasker_adapter.py`. It requires a primary SUT
answer before follow-up generation. The original QAAskeR Q2S/S2G MR2 modules
run in the isolated `.venv310` environment through a persistent subprocess:

```powershell
python 1号机代码/DATA_new/analysis/rq1_error_detection/run_qaasker_evaluation.py `
  --mode MPLUG `
  --vlm-call-budget 1000 `
  --frame-pool-size 100 `
  --output-dir 1号机代码/DATA_new/analysis/qaasker_results/mplug_1000
```

The runner reserves two calls per complete pair: one primary question and one
follow-up derived from the SUT's primary answer. It does not use the old
offline selector approximation.

Cross-paradigm methods are compared using:

- unique verified failures per VLM call;
- calls per new failure;
- failure category diversity;
- duplicate failure rate;
- failure distribution across frames and scene concepts.

Their structural coverage can be reported as a diagnostic, but it is not a
cross-method ranking metric.

## Budget Contract

The experiment uses two explicit, non-interchangeable budgets:

- `generation_budget`: number of questions emitted while building a suite.
  It is used for structural coverage and generation-capacity comparisons.
- `vlm_call_budget`: number of tested-model inference calls. It is used for
  cross-paradigm error-detection comparisons. QAAskeR consumes two calls per
  complete primary/follow-up pair; deterministic generators consume no calls
  until their emitted questions are evaluated.

The final report contains three separate tables:

- Table A: structural coverage at an equal generation budget.
- Table B: error detection at the same actual VLM-call count for every method.
- Table C: capacity under a requested VLM-call ceiling, showing actual calls
  when a method exhausts its suite before reaching that ceiling.

## Leakage Enforcement

`experiment_protocol.py` records provenance and rejects ADVTEST-private fields
from external-baseline records. Every emitted question records its layer,
method, source, adapter, sample token, coverage-feedback usage, and VLM-call
cost.

The complete protocol is documented in:

`docs/superpowers/specs/2026-06-12-rq1-experiment-boundaries-design.md`

## VLM Evaluation

Evaluate generated suites with `run_suite_evaluation.py`. Use VLM calls, not
question pairs, as the common budget when QAAskeR is included.

```powershell
python 1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py `
  --suite-dir 1号机代码/DATA_new/analysis/fixed_budget_results/v2_structural `
  --mode MPLUG `
  --vlm-call-budget 1000 `
  --output-dir 1号机代码/DATA_new/analysis/suite_eval_results/v2_structural_mplug
```

The report separates wrong question count from independent failures. Multiple
QATest mutations of the same official seed count as one independent failure,
and the primary cross-paradigm metric is `unique_failures_per_100_calls`.

Build the three tables after generation and evaluation:

```powershell
python 1号机代码/DATA_new/analysis/rq1_error_detection/experiment_tables.py `
  --structural-summary <fixed_budget_summary.json> `
  --common-results <equal_call_suite_summary.json> <qaasker_summary.json> `
  --capacity-results <capacity_suite_summary.json> `
  --requested-vlm-call-budget 1000 `
  --output-dir <table_output_dir>
```

## Tests

```powershell
cd 1号机代码/DATA_new/analysis/rq1_error_detection
python -m unittest discover -p "test_*.py" -v
```

## SFT Export

`export_sft_dataset.py` remains responsible for compiling VQA pairs and camera
mosaics for fine-tuning. It is independent of the RQ1 baseline boundary.
