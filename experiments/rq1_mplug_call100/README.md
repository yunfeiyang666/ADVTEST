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
