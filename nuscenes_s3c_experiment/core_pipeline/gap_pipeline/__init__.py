"""
gap_pipeline — Coverage-driven gap QA generation pipeline.

Modules
-------
config
    LLM settings + ID-based scene-analysis and gap-context Cypher prompts.
llm_client
    LLMClient: generate_scene_analysis_cypher() / generate_gap_context_cypher().
gap_templates
    75-template × 4-variant library; get_applicable_templates(), resolve_answer().
scene_coverage
    CoverageMap  — ID-keyed coverage counter (edge / L2A / L2B cells).
    SceneCoverageCalculator — build_coverage_map(llm_client), get_gap_cells().
gap_qa_generator
    GapQAGenerator — generate_from_gap_cells(gap_cells) → list of QA dicts.
    fill_gap_cells() — one-call convenience wrapper.

Typical usage
-------------
    from neo4j import GraphDatabase
    from core_pipeline.gap_pipeline.llm_client import LLMClient
    from core_pipeline.gap_pipeline.scene_coverage import SceneCoverageCalculator
    from core_pipeline.gap_pipeline.gap_qa_generator import GapQAGenerator

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    llm    = LLMClient()

    calc   = SceneCoverageCalculator(driver)
    cmap   = calc.build_coverage_map(llm)          # one edge cell per graph edge

    gen    = GapQAGenerator(llm, driver)
    gaps   = cmap.get_gap_cells(level="edge")       # uncovered edges
    qa_pairs = gen.generate_from_gap_cells(gaps)

    for qa in qa_pairs:
        cmap.update(qa)                            # mark covered

    print(cmap.stats())
"""
