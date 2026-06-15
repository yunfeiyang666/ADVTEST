# mPLUG-Owl2 Call-100 Evaluation

## Input Decision

The call-100 evaluation uses the first 100 calls from each frozen 1000-question
suite. Questions are not reordered or frame-balanced after generation.

This preserves the behavior being tested:

- ADVTEST and Random both use the shared frame order and the common 50-question
  frame cap. Their first 100 calls therefore cover the same two frames and form
  a controlled internal ablation.
- Official QA and QATest-adapted retain their independent natural ordering.
  Their wider frame distributions are part of their end-to-end behavior.

Reordering all methods into a shared round-robin frame sample would make the
input visually balanced, but it would replace each method's scheduling behavior
with a new shared selector. That is not used here.

## Prefix Distribution

| Method | Questions | Frames | Max/frame |
|---|---:|---:|---:|
| `advtest` | 100 | 2 | 50 |
| `random` | 100 | 2 | 50 |
| `official_qa` | 100 | 6 | 24 |
| `qatest_adapted` | 100 | 53 | 5 |

The final report must retain these frame counts. ADVTEST versus Random supports
an internal ordering-ablation claim. Cross-paradigm results support an
end-to-end testing-efficiency comparison, with GT granularity and frame
distribution disclosed as limitations.

The exact machine-readable audit is in `input_distribution.json`.

## Preflight

The strict preflight passed all four 100-call suites. It resolved 55 unique
real mosaics and found no missing GT, provenance, scene graph, or camera input.

The first attempt exposed a validator defect: identical official question text
on different frames was treated as a duplicate. Those records have different
visual inputs and are valid independent tests. Commit `eea1870` changed the
duplicate key to `(scene_frame, normalized_question)` and added a regression
test. The second attempt passed.

## Recorded Run

- Run ID: `mplug-four-methods-call100`
- Status: completed
- Exit code: 0
- Generation/evaluation commit: `36a4591919866671e13af290925d33e416e05cc0`
- Total wall time: 2985.934 seconds, approximately 49.8 minutes
- Actual real inference records: 400
- Mock fallback records: 0

Every raw record has `mode=MPLUG`, a non-empty model output, `error=null`, and
a positive inference duration.

## Results

| Method | Role | Calls | Wrong | Unique failures | UF/100 | Calls/UF | Duplicate rate | Failed L2 | Frames |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `advtest` | proposed | 100 | 92 | 92 | 92 | 1.087 | 0.000 | 236 | 2 |
| `random` | internal ablation | 100 | 86 | 86 | 86 | 1.163 | 0.000 | 169 | 2 |
| `official_qa` | neutral reference | 100 | 65 | 65 | 65 | 1.538 | 0.000 | N/A | 6 |
| `qatest_adapted` | external comparison | 100 | 60 | 56 | 56 | 1.786 | 0.067 | N/A | 53 |

Average real inference time per question:

| Method | Average | Minimum | Maximum |
|---|---:|---:|---:|
| `advtest` | 8.896 s | 1.986 s | 17.326 s |
| `random` | 6.363 s | 2.847 s | 12.622 s |
| `official_qa` | 7.396 s | 2.908 s | 25.991 s |
| `qatest_adapted` | 5.743 s | 2.759 s | 12.800 s |

## Interpretation

The controlled internal ablation compares ADVTEST and Random on the same two
frames and equal 100-call budget:

- ADVTEST found 92 independent failures versus Random's 86, a gain of 6
  failures or 6.98% relative to Random.
- ADVTEST exposed 236 failed L2 items versus Random's 169, a gain of 67 items
  or 39.64% relative to Random.

This supports the claim that coverage-guided ordering improves failure
discovery over random ordering within the shared generated-question space.

The cross-paradigm rows are descriptive. Official QA and QATest-adapted use
category-level GT and different natural frame distributions, while ADVTEST
uses instance-level and relational GT. Their raw failure rates must not be
presented as a difficulty-controlled head-to-head accuracy comparison.

## Limitations

- The checkpoint loader again reported newly initialized visual-abstractor q/k
  positional embedding weights.
- Correctness uses normalized answer containment rather than semantic judging.
- This is one deterministic frozen-prefix run; Random variance and repeated-run
  confidence intervals are not yet available.
- QATest-adapted generated 60 wrong answers but only 56 independent failures,
  confirming that mutations of the same official seed can duplicate a failure.

Raw logs, mosaics, suites, manifests, and per-question outputs remain under
`scratch/rq1_mplug_call100/`.
