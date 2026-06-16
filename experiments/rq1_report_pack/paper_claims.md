# RQ1 Claim-to-Evidence Notes

## Recommended Main Framing

Under an equal 1000-question / 1000-VLM-call budget, ADVTEST's coverage-guided question selection finds more and structurally broader VLM failures than random candidate selection.

## Claims

### supported_by_call1000_internal_ablation

Claim: Under the same 1000-question / 1000-VLM-call budget, coverage-guided ADVTEST detects more unique VLM failures than random candidate selection.

Evidence: ADVTEST finds +69 unique failures over Random (7.57%).

### supported_by_frame_qualified_l2_metrics

Claim: ADVTEST's advantage is stronger on structural error coverage than on raw unique-failure count.

Evidence: Failed unique L2 increases by +1761 (64.58%), while input covered L2 increases by +1690 (59.97%).

### supported_by_random_seed_variance

Claim: The ADVTEST-vs-Random trend is not explained by one lucky Random seed in the call100 pilot.

Evidence: At 100 calls, ADVTEST exceeds all 3 Random seeds on unique failures and failed unique L2.

### boundary_condition

Claim: Official NuScenes-QA and QATest-adapted should be described as external references, not coverage-comparable head-to-head baselines.

Evidence: Both use category-level official ground truth and do not expose ADVTEST-private structural L2 coverage footprints.

## Caveats To Preserve In Paper Text

- Official NuScenes-QA and QATest-adapted are external references, not the main coverage-comparable baselines.
- Correctness is currently deterministic token-boundary lexical scoring, not semantic judging.
- Structural L2 metrics are frame-qualified; this is intentional to avoid merging same-named objects across frames.
