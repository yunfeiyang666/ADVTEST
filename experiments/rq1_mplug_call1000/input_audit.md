# RQ1 Call-1000 Input Audit

- Budget: 1000 actual VLM calls per method
- Selection: frozen_suite_prefix

## Methods

| Method | Calls | Frames | Max/frame | GT granularity | Coverage comparable | Covered L2 | Micro L2 | L2/Q |
|---|---:|---:|---:|---|---|---:|---:|---:|
| `advtest` | 1000 | 20 | 50 | instance_or_relation | True | 4508 | 0.004383 | 4.508 |
| `random` | 1000 | 20 | 50 | instance_or_relation | True | 2818 | 0.002740 | 2.818 |
| `official_qa` | 1000 | 67 | 28 | category_level_official | False | N/A | 0.000000 | 0.000 |
| `qatest_adapted` | 1000 | 100 | 29 | category_level_official | False | N/A | 0.000000 | 0.000 |

## Internal Ablation

- ADVTEST minus Random covered L2: 1690
- Relative micro-L2 gain: 59.97%
- L2/Q gain: 1.690

## Comparison Boundaries

- ADVTEST versus Random is the structurally comparable internal ablation.
- Official QA and QATest-adapted are cross-paradigm references; they do not expose structural L2 coverage.
- Cross-paradigm failure rates must report GT granularity and frame distribution.
