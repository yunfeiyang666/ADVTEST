"""Inspect objects that share the same status as the trailer in scene-0553_frame8.

Assumes the scene-0553_frame8 scene graph has already been imported into Neo4j
(just ran tmp_run_core_examples.py or equivalent).
"""
from neo4j import GraphDatabase

URI = "bolt://localhost:7600"
AUTH = ("neo4j", "87017563")


def main():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        # Trailer basic info
        print("[Trailer info]")
        res = session.run(
            """
            MATCH (t:Object)
            WHERE t.category CONTAINS 'trailer'
            RETURN t.unique_id AS id, t.type AS type, t.status AS status
            """
        )
        trailers = list(res)
        for r in trailers:
            print(f"  trailer id={r['id']}, type={r['type']}, status={r['status']}")

        # All objects with same status (including trailer itself)
        print("\n[All objects with same status as trailer (including trailer itself)]")
        res = session.run(
            """
            MATCH (t:Object)
            WHERE t.category CONTAINS 'trailer'
            WITH t.status AS trailerStatus
            MATCH (o:Object)
            WHERE o.status = trailerStatus
            RETURN o.type AS type, count(*) AS c
            ORDER BY c DESC, type
            """
        )
        for r in res:
            print(f"  type={r['type']}, count={r['c']}")

        # All *other* objects (excluding the trailer node itself) with same status
        print("\n[Other objects (excluding the trailer node itself) with same status]")
        res = session.run(
            """
            MATCH (t:Object)
            WHERE t.category CONTAINS 'trailer'
            WITH t.status AS trailerStatus, t.unique_id AS trailerId
            MATCH (o:Object)
            WHERE o.status = trailerStatus AND o.unique_id <> trailerId
            RETURN o.type AS type, count(*) AS c
            ORDER BY c DESC, type
            """
        )
        total_other = 0
        for r in res:
            print(f"  type={r['type']}, count={r['c']}")
            total_other += r["c"]
        print(f"  TOTAL other count = {total_other}")

        # Breakdown by including/excluding some candidate types
        print("\n[Heuristic subsets for candidate QA semantics]")
        subsets = {
            "dynamic_only": ["car", "truck", "bus", "bicycle", "motorcycle", "pedestrian", "trailer"],
            "no_barrier": ["car", "truck", "bus", "bicycle", "motorcycle", "pedestrian", "trailer", "ego"],
            "vehicles_only": ["car", "truck", "bus", "bicycle", "motorcycle", "trailer"],
        }
        for name, types in subsets.items():
            res = session.run(
                """
                MATCH (t:Object)
                WHERE t.category CONTAINS 'trailer'
                WITH t.status AS trailerStatus, t.unique_id AS trailerId
                MATCH (o:Object)
                WHERE o.status = trailerStatus
                  AND o.unique_id <> trailerId
                  AND o.type IN $types
                RETURN count(o) AS c
                """,
                types=types,
            )
            c = res.single()["c"]
            print(f"  subset={name}, types={types}, count={c}")

    driver.close()


if __name__ == "__main__":
    main()
