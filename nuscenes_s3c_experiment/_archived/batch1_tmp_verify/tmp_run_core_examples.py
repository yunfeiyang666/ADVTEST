"""Quick script to probe a few core failed questions on scene-0553_frame8
using the current geometry/type/prompt setup but a minimal, safe normalizer.
"""
import os
import json

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
import config as root_config


class DummyNormalizer:
    """Minimal normalizer: do almost nothing, only detect a coarse question_type.

    This bypasses current QuestionNormalizer bugs so we can inspect geometry/type effects.
    """

    def normalize(self, question: str):
        q = question.strip()
        qt = self._detect_type(q)
        return q, qt

    def _detect_type(self, q: str) -> str:
        q_lower = q.lower()
        if q_lower.startswith("are there") or q_lower.startswith("are any") or q_lower.startswith("is there"):
            return "exist"
        if q_lower.startswith("how many") or q_lower.startswith("what number"):
            return "count"
        if " same status as " in q_lower or "same as" in q_lower:
            return "comparison"
        if "status" in q_lower:
            return "status"
        return "object"

    def get_expected_format(self, question_type: str) -> str:
        if question_type == "exist" or question_type == "comparison":
            return 'Answer with "yes" or "no" only.'
        if question_type == "count":
            return 'Answer with a number only (e.g., "5").'
        if question_type == "status":
            return 'Answer with a status word only (e.g., "stopped", "moving", "with rider", "without rider").'
        if question_type == "object":
            return 'Answer with the object type only (e.g., "car", "pedestrian", "bicycle").'
        return 'Answer concisely with the key information only.'


def import_scene_0553_frame8():
    """Import scene-0553_frame8 scene graph into Neo4j using current JSON."""
    scene_graph_path = os.path.join(
        root_config.OUTPUT_DIR,
        "coverage_analysis",
        "scene_graphs",
        "scene-0553_frame8_scene_graph.json",
    )
    with open(scene_graph_path, "r", encoding="utf-8") as f:
        scene_graph = json.load(f)

    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    try:
        print("[Neo4j] Clearing and importing scene-0553_frame8 ...")
        importer.clear_database()
        importer.create_constraints()
        importer.import_scene(scene_graph)
        print("[Neo4j] Import done.")
    finally:
        importer.close()


def main():
    # 1) Import the scene graph
    import_scene_0553_frame8()

    # 2) Build VQAPipeline and plug in DummyNormalizer
    pipeline = VQAPipeline(use_ir=False)
    if not pipeline.initialize():
        print("Pipeline init failed.")
        return

    pipeline.question_normalizer = DummyNormalizer()

    # 3) Core example questions on scene-0553_frame8
    examples = [
        # status / 8-direction around pedestrian
        "What status is the car to the back right of the not standing pedestrian?",
        # truck back of ego
        "There is a truck that is to the back of me; what is its status?",
        # barriers in front of trailer
        "How many barriers are to the front of the trailer?",
        # same-status count for trailer
        "What number of other things are there of the same status as the trailer?",
    ]

    for i, q in enumerate(examples, 1):
        print("\n" + "-" * 80)
        print(f"Example {i}")
        print(f"Q: {q}")
        result = pipeline.process_question(q, verbose=True)
        print("\nResult summary:")
        print(f"  success       : {result.success}")
        print(f"  answer        : {result.answer}")
        print(f"  cypher        : {result.cypher_query}")
        print(f"  error         : {result.error}")


if __name__ == "__main__":
    main()
