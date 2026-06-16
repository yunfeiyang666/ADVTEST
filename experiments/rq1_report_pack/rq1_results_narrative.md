# RQ1 Results Narrative

## Main Finding

At the formal 1000-question / 1000-VLM-call budget, ADVTEST finds 981 unique failures versus 912 for Random (+69, 7.57%).

The larger effect appears in structural coverage: ADVTEST touches 4488 failed unique L2 items versus 2727 for Random (+1761, 64.58%). Its generated questions also cover +1690 input L2 items over Random (59.97%).

## Manual Audit Interpretation

The manual audit reviewed 48 sampled failure rows. 33 were judged valid visual/structural failures (68.8%), while 15 were boundary cases.

Random-only samples have a slightly higher sampled validity rate (75.0%) than ADVTEST-only samples (66.7%). This should not be read as Random being better overall, because the exclusive structural space is much smaller for Random.

## Adjusted Effective Failure Estimate

Using the manual audit only as a qualitative extrapolation, ADVTEST-only failed L2 has about 2046.7 estimated valid structural failures (3070 * 66.7%), whereas Random-only has about 981.8 (1309 * 75.0%).

Thus, even with Random-only's slightly higher sampled validity rate, ADVTEST's larger exclusive structural space gives an estimated +1064.9 additional valid exclusive failed L2 items (~2.08x Random-only).

## Limitations

- The adjusted estimate is qualitative and based on a small audit sample.
- Correctness is still deterministic token-boundary lexical scoring.
- Instance-level answers are strict; rows marked answer-granularity mismatch should not be counted as strong visual failures.
- The mosaics do not render object IDs, so the review is scene-graph-assisted rather than purely visual.

## Paper-Ready Paragraph

Under an equal 1000-question budget, ADVTEST identifies broader structural failure coverage than random candidate selection. It finds 981 unique failures compared with 912 for Random (+69, 7.57%), and its failed unique L2 coverage is 4488 versus 2727 (+1761, 64.58%). A manual audit of 48 sampled failures shows that both ADVTEST-only and Random-only samples contain valid structural errors as well as answer-format boundary cases. Random-only has a slightly higher sampled validity rate, but its exclusive failed L2 space is much smaller; a qualitative extrapolation estimates 2047 valid ADVTEST-only failed L2 items versus 982 for Random-only. We therefore interpret ADVTEST's advantage as a coverage-breadth effect rather than a per-sample validity effect.
