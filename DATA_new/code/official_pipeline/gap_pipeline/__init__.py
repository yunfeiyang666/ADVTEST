"""
gap_pipeline — New core modules for coverage-driven gap QA generation.

The active L2 definition is the unified three-node gap:

    a|b|c

Legacy L2A/L2B concepts are intentionally removed from the core package. Old
LLM/Cypher pipeline code lives under `_archive/legacy_pipeline/` for reference.

Main L2 refactor modules:

- l2_taxonomy: template-family metadata and ego slot rules
- l2_geometry: official-direction, distance, and viewpoint helpers
- l2_candidate_builder: normalized candidate-set builders
- l2_constraint_planner: REG-style uniqueness planner
- l2_question_realizer: deterministic question templates
- l2_question_graph: explicit subgraph coverage footprint
- l2_cypher_builders: programmatic candidate/verify Cypher builders
- l2_dry_run: feasibility dry-run composition layer
- l2_sampler: weighted feasible-plan sampler
- l2_adapter: bridge from dry-run plan to QA record
"""
