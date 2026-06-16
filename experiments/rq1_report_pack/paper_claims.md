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

### supported_by_manual_audit_with_caveat

Claim: ADVTEST's advantage should be interpreted as coverage breadth, not higher per-sample validity.

Evidence: In the 48-row manual audit, Random-only samples have a slightly higher sampled validity rate than ADVTEST-only samples (75.0% vs. 66.7%). However, ADVTEST has a much larger exclusive failed-L2 space (3070 vs. 1309). A qualitative extrapolation estimates about 2047 valid ADVTEST-only failed L2 items versus about 982 for Random-only.

### boundary_condition

Claim: Official NuScenes-QA and QATest-adapted should be described as external references, not coverage-comparable head-to-head baselines.

Evidence: Both use category-level official ground truth and do not expose ADVTEST-private structural L2 coverage footprints.

## Caveats To Preserve In Paper Text

- Official NuScenes-QA and QATest-adapted are external references, not the main coverage-comparable baselines.
- Correctness is currently deterministic token-boundary lexical scoring, not semantic judging.
- Structural L2 metrics are frame-qualified; this is intentional to avoid merging same-named objects across frames.
- Manual audit estimates are qualitative and small-sample; use them to explain result interpretation, not as a statistical significance claim.
