# GAP Pipeline v7 Neo4j Set-Cover Handoff

## 1. Current objective

The current v7 goal is **not** one question per gap. The goal is:

> Under real Neo4j constraints and verified coverage footprints, generate as few QA items as possible while covering the complete L2 gap universe.

Formal family distribution is evaluated on the `formal_selected` phase. Extra questions used only to complete coverage are marked as `coverage_backfill`.

## 2. Final recommended run output

Use this directory as the current official trial result:

```text
outputs/v7_final_neo4j_setcover
```

Main files:

```text
outputs/v7_final_neo4j_setcover/scene-0103_frame0/reports/scene-0103_frame0_summary.json
outputs/v7_final_neo4j_setcover/scene-0103_frame0/generation/qa/scene-0103_frame0_generated.jsonl
outputs/v7_final_neo4j_setcover/scene-0103_frame0/reports/scene-0103_frame0_incremental_coverage.csv
outputs/v7_final_neo4j_setcover/scene-0103_frame0/reports/scene-0103_frame0_incremental_coverage.jsonl
```

The old directory below should not be used as the final result:

```text
outputs/v7_final_from_offline
```

It was geometry/offline based and had much worse L2 coverage.

## 3. Final confirmed metrics

Latest official result:

```json
{
  "generated": 992,
  "total_gap_count": 1092,
  "covered_gap_count": 1092,
  "uncovered_gap_count": 0,
  "failed_candidate_count": 0,
  "tried_candidate_count": 992,
  "pool_source": "neo4j_full_gap_universe",
  "verification": {"NEO4J_EXECUTED": 992},
  "coverage": {"l0": 14, "l1": 91, "l2": 1092}
}
```

Core conclusion:

```text
992 Neo4j-verified QA items cover all 1092 L2 gaps.
```

This demonstrates set-cover behavior because:

```text
generated < total L2 gaps
992 < 1092
```

## 4. Two-phase selection policy

Each generated QA has:

```json
"selection_phase": "formal_selected"
```

or:

```json
"selection_phase": "coverage_backfill"
```

### formal_selected

Formal ratio-controlled subset:

```json
{
  "formal_selected_count": 493,
  "formal_covered_gap_count": 593,
  "formal_actual": {
    "converge": 169,
    "diverge_compare": 177,
    "direction_chain": 59,
    "distance_chain": 59,
    "viewpoint_transfer": 29
  }
}
```

Formal ratios:

```json
{
  "converge": 0.3428,
  "diverge_compare": 0.3590,
  "direction_chain": 0.1197,
  "distance_chain": 0.1197,
  "viewpoint_transfer": 0.0588
}
```

Interpretation:

```text
converge + diverge_compare ~= 70%
direction_chain ~= 12%
distance_chain ~= 12%
viewpoint_transfer ~= 6%
```

### coverage_backfill

Backfill is used to complete the universe coverage:

```json
{
  "coverage_backfill_count": 499,
  "coverage_backfill_actual": {
    "direction_chain": 227,
    "distance_chain": 136,
    "viewpoint_transfer": 136
  },
  "backfill_balance_relaxed": true
}
```

Backfill is balanced first; if coverage is still incomplete, balance caps are relaxed to force complete L2 coverage.

## 5. LLM usage status

The current official result does **not** use LLM generation.

Current run uses:

```text
ADVTEST_INITIAL_COVERAGE_LLM=false
```

Meaning:

| Stage | LLM used? | Notes |
|---|---:|---|
| initial coverage | No | deterministic replay / fallback |
| QA verbalization | No | template adapter |
| candidate selection | No | greedy set-cover |
| verification | No | Neo4j Bolt Cypher |

`gap_pipeline/l2_llm_client.py` exists, and `LLMClient` can be enabled through `use_llm`, but the current official fast run is deterministic/template-based.

## 6. Major code changes made

### Neo4j Bolt path

`run_gap_pipeline_v7.py` now uses official Neo4j Bolt driver for verify/query and also imports scene graph via Bolt. HTTP 7474 import is no longer required.

### Diverge verification fix

Files:

```text
gap_pipeline/l2_cypher_builders.py
gap_pipeline/l2_adapter.py
```

Diverge verification was changed from global branch uniqueness to pair verification:

```text
verify specified b->a and b->c relations, direction, type, and status
```

This fixed the large diverge failure rate.

### Direction alignment

`DryRunInput` now carries graph-edge directions:

```text
a_to_b_dir, c_to_b_dir, b_to_a_dir, b_to_c_dir
```

Adapters prefer graph relationship direction over geometry fallback.

### Greedy set-cover selection

Selection is coverage-driven, not gap-driven. Candidate attempt keys use:

```text
gap + family + footprint + answer
```

This prevents one failed family from blocking other candidates for the same gap.

### Two-phase output

The selector now separates:

```text
formal_selected: strict family-ratio layer
coverage_backfill: full universe completion layer
```

### Initial coverage cleanup

File:

```text
gap_pipeline/l2_initial_coverage_analyzer.py
```

Empty fallback is no longer marked as `GROUNDED`. It is now reported as:

```text
UNRESOLVED_RECORD_FALLBACK_EMPTY
```

Deterministic mismatches are reported as:

```text
DETERMINISTIC_ANSWER_MISMATCH
```

Current initial coverage is a conservative lower bound, not full semantic recovery.

## 7. Incremental coverage report

A new function was added:

```python
emit_incremental_coverage_report(...)
```

It writes per-question coverage contribution in chronological/question order.

Generated files:

```text
reports/scene-0103_frame0_incremental_coverage.csv
reports/scene-0103_frame0_incremental_coverage.jsonl
```

Important columns:

```text
order_index, question_id, selection_phase, l2_family,
raw_l0, raw_l1, raw_l2,
delta_l0, delta_l1, delta_l2,
cum_l0, cum_l1, cum_l2,
coverage_rate_l0, coverage_rate_l1, coverage_rate_l2,
new_l0, new_l1, new_l2
```

Use for plots:

```text
x = order_index
y = cum_l2 or coverage_rate_l2
```

`delta_l*` is the non-duplicated new contribution of the current question, after excluding gaps already covered by previous questions.

## 8. Current analysis finding: why later delta_l2 is mostly 1

The incremental CSV shows most later questions add exactly one new L2. This is expected under current footprint definitions.

Observed distribution:

```text
delta_l2 = 1 for most selected QAs
multi-L2 contribution mainly comes from converge
```

Reason:

- `converge_graph` can create multiple length-2 paths through refs, so raw L2 can be 3 or 6.
- `direction_chain`, `distance_chain`, and `viewpoint_transfer` currently use a simple chain graph `a-b-c`, so raw L2 is usually exactly 1.
- `diverge_compare` currently verifies well but usually contributes raw L2 = 1 because selected diverge plans rarely include reference clauses that form extra L2 paths.

This means the pipeline is correct but conservative. To improve set-cover compression further, next work should enrich diverge/chain/viewpoint footprints with verified reference constraints.

## 9. Candidate potential report status

A candidate-level potential report function was started:

```python
emit_candidate_potential_report(...)
```

Intended outputs:

```text
reports/scene-0103_frame0_candidate_potential.csv
reports/scene-0103_frame0_candidate_potential.jsonl
```

Purpose:

```text
For every feasible candidate, record raw_l0/raw_l1/raw_l2 and whether it was selected.
```

This will tell us whether multi-L2 candidates exist but were not selected, or whether current templates simply do not generate many multi-L2 candidates.

Important: code currently compiles after the latest edits, but this candidate report should be verified by a fresh run before using it for analysis.

## 10. Re-run command

From:

```text
DATA_new/code/official_pipeline
```

Run:

```powershell
$env:ADVTEST_INITIAL_COVERAGE_LLM='false'
python run_gap_pipeline_v7.py --plan full --artifact-root outputs\v7_final_neo4j_setcover --plan-file plans\test_2frame.json --frame-index 0
```

Neo4j Bolt must be running at:

```text
bolt://127.0.0.1:7687
```

## 11. Recommended next steps

1. Re-run `outputs/v7_final_neo4j_setcover` once to regenerate candidate potential reports.
2. Plot incremental coverage from `scene-0103_frame0_incremental_coverage.csv`.
3. Inspect candidate potential report to see if unselected multi-L2 candidates exist.
4. If multi-L2 potential is low, extend templates/footprints:
   - diverge with verified refs
   - chain with verified ref constraints
   - viewpoint transfer with verified ref constraints
5. Keep formal ratio evaluation based on `selection_phase == formal_selected`.

