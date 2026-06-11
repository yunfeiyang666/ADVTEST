import os
import json

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline


def main():
    print("=== Quick VQA smoke test on one question (scene-0553_frame8, Q8) ===")

    # 1) Load scene graph for scene-0553_frame8
    sg_path = os.path.join(
        config.OUTPUT_DIR,
        "coverage_analysis",
        "scene_graphs",
        "scene-0553_frame8_scene_graph.json",
    )
    print(f"Loading scene graph: {sg_path}")
    with open(sg_path, "r", encoding="utf-8") as f:
        scene_graph = json.load(f)

    # 2) Import into Neo4j
    print("\n[Step A] Import scene into Neo4j...")
    # Use same hard-coded Neo4j connection as other test scripts
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    try:
        importer.clear_database()
        importer.create_constraints()
        importer.import_scene(scene_graph)
        with importer.driver.session() as session:
            node_count = session.run("MATCH (n:Object) RETURN count(n) AS c").single()["c"]
            rel_count = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c").single()["c"]
        print(f"Imported {node_count} nodes, {rel_count} relations.")
    finally:
        importer.close()

    # 3) Initialize VQA pipeline
    print("\n[Step B] Initialize VQA Pipeline...")
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("Pipeline initialization failed.")
        return

    # 4) Ask a single hard question (Q8)
    question = (
        "Is the status of the bus to the back right of the not standing pedestrian "
        "the same as the bus that is to the front of the stopped trailer?"
    )
    print("\n[Step C] Run single question:")
    print(question)

    result = pipeline.process_question(question, verbose=True)
    print("\n=== VQAResult ===")
    print(result.to_json())


if __name__ == "__main__":
    main()
