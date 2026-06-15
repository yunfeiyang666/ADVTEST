# mPLUG Formal Evaluation Preflight Design

## Goal

Prepare and execute a trustworthy mPLUG-Owl2 RQ1 evaluation without allowing
missing images, model-loading failures, or inference failures to silently fall
back to mock predictions.

The first real-VLM stage is a 20-call smoke run per method. A 100-call run is
allowed only after every smoke suite passes preflight and real inference.
Running the final 1000-call experiment is outside this stage.

## Evaluated Methods

The smoke comparison contains four explicitly separated roles:

- `advtest`: the proposed structural testing method;
- `random`: an internal ordering ablation;
- `official_qa`: the neutral official NuScenes-QA reference;
- `qatest_adapted`: the independent QATest comparison.

`random` is not presented as an external baseline. `official_qa` is not
presented as a generation method. The report must retain these roles instead
of placing all four methods under one undifferentiated baseline label.

## Budget

The common comparison budget is the number of actual mPLUG-Owl2 inference
calls. Each record in these four suites costs one call.

The smoke run uses:

```text
vlm_call_budget = 20 per method
```

Offline suite generation time does not consume this budget. Cached answers may
not reduce the reported call count unless a real model response from the same
model configuration is deliberately reused and recorded as such. The smoke
run should therefore use fresh per-question inference.

## Preflight Contract

Before constructing the VLM evaluator, the preflight command validates each
selected suite.

For every suite it must verify:

1. the file exists and contains at least the requested call budget;
2. every record has a non-empty question and ground-truth answer;
3. `vlm_call_cost` is a positive integer and the requested prefix can consume
   exactly 20 calls;
4. provenance fields required by the experiment boundary are present;
5. normalized question text is unique within the evaluated prefix;
6. official-derived records preserve a source question ID;
7. every evaluated record resolves to a real scene frame;
8. every scene frame has a scene graph;
9. a six-camera mosaic can be resolved from real NuScenes image files;
10. no generated placeholder or mock image is accepted as real visual input.

Preflight emits a JSON report containing suite paths, record counts, call
capacity, unique frames, image availability, failures, and the input file
hashes. Any failure produces a non-zero exit code and blocks evaluation.

## Strict Real-VLM Behavior

`run_suite_evaluation.py` gains a strict-real-input boundary.

For `MPLUG` mode:

- missing mosaics raise an error;
- failed mosaic rendering raises an error;
- model loading failure raises an error;
- inference failure raises an error;
- mock fallback is forbidden;
- the raw result records the prompt, model mode, elapsed inference time,
  original model output, correctness decision, and any error context.

`MOCK` mode remains available for unit tests and offline pipeline checks. No
change should make mock behavior appear in an `MPLUG` report.

The existing `LOCAL_GPU`, `MINICPM`, and `API` modes are outside this stage.

## Suite Assembly

The smoke runner consumes a dedicated suite directory containing only the four
approved suite files. It may copy or materialize deterministic prefixes from
existing generated suites, but it must not alter their question content,
answers, provenance, or ordering.

The input sources are:

- the formal structural-generation results for `advtest` and `random`;
- the formal official-QA suite for `official_qa`;
- the audited QATest-adapted suite for `qatest_adapted`.

The assembly manifest records the source path and SHA-256 for each suite.

## Execution and Tracking

The real smoke must run through `run_recorded_experiment.py`. The manifest
records:

- Git commit and branch;
- suite and frame-cache hashes;
- model mode `MPLUG`;
- actual command;
- requested and actual call counts;
- start, finish, and elapsed times;
- stdout and stderr paths;
- final status.

Raw per-question results remain under `scratch/`. A compact audited summary and
run index are committed under `experiments/rq1_mplug_smoke/`.

No remote push is part of this stage.

## Metrics

The report keeps failure rate for diagnosis but uses testing-efficiency
metrics for cross-method comparison:

- actual VLM calls;
- wrong answers;
- unique verified failures;
- unique failures per 100 calls;
- calls per unique failure;
- duplicate failure rate;
- failure category count;
- visited frames;
- inference duration.

Structural L2 coverage remains meaningful for ADVTEST and Random diagnostics.
It must not be used to rank Official QA or QATest-adapted.

## Tests

Automated tests must prove:

- preflight rejects missing suites and insufficient call capacity;
- preflight rejects missing questions, answers, provenance, and source IDs;
- preflight rejects duplicate normalized questions in the evaluated prefix;
- preflight rejects unresolved scene graphs and mosaics;
- MPLUG evaluation raises instead of using Mock when an image is missing;
- raw results include prompt, mode, output, and elapsed time;
- MOCK mode remains usable for existing unit tests;
- all existing RQ1 regression tests remain green.

## Stop Conditions

Stop and report before launching or continuing real inference when:

- any preflight check fails;
- mPLUG-Owl2 does not load on the RTX 3070;
- a real question lacks a real mosaic;
- CUDA out-of-memory occurs;
- any MPLUG record contains evidence of mock fallback;
- actual call accounting differs from the requested 20 calls.

The 100-call expansion requires all four 20-call suites to complete under this
contract.
