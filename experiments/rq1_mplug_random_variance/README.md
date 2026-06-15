# mPLUG-Owl2 Random-Seed Variance Plan

## Goal

Measure whether the call-100 ADVTEST versus Random result depends materially on
the Random generator seed.

The fixed comparison keeps the following conditions unchanged:

- 100 actual mPLUG-Owl2 calls per Random seed;
- the same 100-frame pool and frame order;
- the selected 50-question per-frame cap;
- the first 100 questions from each frozen generated suite;
- the same model checkpoint, 4-bit loading path, image resolver, and
  `token_boundary_v2` scorer.

## Runs

The completed seed-42 Random result is reused from
`mplug-four-methods-call100`; its 100 real calls are not repeated.

Two additional recorded runs are required:

| Run ID | Seed | Source suite | New real calls |
|---|---:|---|---:|
| `mplug-random-seed43-call100` | 43 | `structural-cap50-seed43-retry1/results/random_suite.jsonl` | 100 |
| `mplug-random-seed44-call100` | 44 | `structural-cap50-seed44-retry1/results/random_suite.jsonl` | 100 |

Each source suite already contains 1000 questions generated under the formal
structural protocol. The evaluator consumes only the exact 100-call prefix.

## Gates

Before inference, both prefixes must pass the strict mPLUG preflight:

- exactly 100 reachable calls;
- non-empty question and ground truth;
- valid method provenance and experiment boundary;
- no duplicate normalized question within the same frame;
- resolvable scene graph and real six-camera mosaic.

The run must fail rather than use Mock fallback when the model or image input is
unavailable.

## Reporting

The final report will combine Random seeds 42, 43, and 44 and publish:

- wrong answers and independent failures for each seed;
- mean, population standard deviation, minimum, and maximum;
- ADVTEST's absolute and relative gain over the Random mean;
- the number of seeds on which ADVTEST exceeds Random;
- all row-level scoring changes, if any.

The result is a three-seed robustness check, not a confidence interval over the
full Random population.
