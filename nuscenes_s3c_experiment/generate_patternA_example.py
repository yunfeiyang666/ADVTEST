"""Example of using abstract Pattern A to generate a comparison query,
execute it on Neo4j, and obtain a canonical yes/no answer.

This is a small demonstration for scene-0553_frame8 using the same
structure as Pattern A (two objects defined by spatial relations and
status comparison). Later this can be generalized and wrapped in a
question-generation pipeline.
"""
from neo4j import GraphDatabase
from pathlib import Path
import json

from vqa_pipeline import config

SCENE_GRAPH_PATH = Path("output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json")


def build_patternA_cypher() -> str:
    """Build a Pattern-A style Cypher.

    Here we hard-code one instance (similar to Q8 semantics) purely as an
    example of how to fill the template:
      - REF1: not-standing pedestrian
      - OBJ1: bus at back-right of REF1
      - REF2: stopped trailer
      - OBJ2: bus at front of REF2
    """
    return """MATCH (ped:Object)
WHERE ped.type='pedestrian' AND ped.status <> 'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object)
WHERE bus1.type='bus' AND r1.predicates[0]='back-right'
WITH ped, bus1, r1
ORDER BY r1.distance ASC
LIMIT 1

MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object)
WHERE bus2.type='bus' AND r2.direction_4='front'
WITH bus1, bus2, r2
ORDER BY r2.distance ASC
LIMIT 1

RETURN bus1.status = bus2.status AS same_status"""


def run_query(cypher: str) -> None:
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            print("Executing Cypher:\n", cypher)
            result = session.run(cypher)
            records = list(result)
            print("\nRaw records:")
            for r in records:
                print(dict(r))
            if not records:
                print("\nCanonical answer: same_status = False (no rows)")
            else:
                same = records[0].get("same_status")
                print(f"\nCanonical answer: same_status = {same}")
    finally:
        driver.close()


if __name__ == "__main__":
    if not SCENE_GRAPH_PATH.exists():
        print(f"Scene graph not found: {SCENE_GRAPH_PATH}")
    else:
        cypher = build_patternA_cypher()
        run_query(cypher)
