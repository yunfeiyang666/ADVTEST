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

## Preflight Result

Both 100-call prefixes passed the strict preflight:

| Seed | Questions | Calls | Frames | Suite SHA-256 |
|---:|---:|---:|---:|---|
| 43 | 100 | 100 | 2 | `beb2aae05ee0dbc59aefc20d34db155fa1b1e46431a12f10e3874c33fa6097fe` |
| 44 | 100 | 100 | 2 | `d1ccf8ee3d0341e5dbb2d0079d9f6c04f4247dd9618a7fd94df7efb4ad22f4e2` |

No missing GT, provenance, scene graph, or real mosaic was reported. The
machine-readable audit is in `preflight_summary.json`.

## Reporting

The final report will combine Random seeds 42, 43, and 44 and publish:

- wrong answers and independent failures for each seed;
- mean, population standard deviation, minimum, and maximum;
- ADVTEST's absolute and relative gain over the Random mean;
- the number of seeds on which ADVTEST exceeds Random;
- all row-level scoring changes, if any.

The result is a three-seed robustness check, not a confidence interval over the
full Random population.

## Recorded Runs

Both additional runs completed with real mPLUG-Owl2 inference:

| Seed | Run ID | Calls | Duration | Mock/error/empty |
|---:|---|---:|---:|---:|
| 43 | `mplug-random-seed43-call100` | 100 | 852.19 s | 0 |
| 44 | `mplug-random-seed44-call100` | 100 | 774.25 s | 0 |

The two runs added 200 real VLM calls. Their manifests, logs, mosaics, and raw
per-question outputs remain under `scratch/rq1_mplug_random_variance/runs/`.
`run_index.json` records input/output hashes and raw-output audit counts.

## Results

All rows use `token_boundary_v2_frame_qualified_l2` scoring over frozen raw
model outputs:

| Method | Seed | Calls | Wrong | Independent failures | Failed unique L2 |
|---|---:|---:|---:|---:|---:|
| ADVTEST | fixed | 100 | 92 | 92 | 236 |
| Random | 42 | 100 | 86 | 86 | 169 |
| Random | 43 | 100 | 88 | 88 | 180 |
| Random | 44 | 100 | 90 | 90 | 183 |

Random statistics across seeds 42, 43, and 44:

| Metric | Mean | Population std | Min | Max |
|---|---:|---:|---:|---:|
| Independent failures | 88.00 | 1.63 | 86 | 90 |
| Failed unique L2 | 177.33 | 6.02 | 169 | 183 |

Compared with the Random mean, ADVTEST found:

- 4.00 more independent failures, a relative gain of 4.55%;
- 58.67 more failed unique L2 items, a relative gain of 33.08%.

ADVTEST exceeded Random on both metrics for all three tested seeds. The
failure-count margin is modest relative to the three-seed range, while the
failed-L2 margin is substantially larger. The evidence therefore supports the
coverage-guidance claim most strongly on structural failure diversity.

The complete machine-readable result, including row-level scoring-change
audits, is in `random_variance_summary.json`.
