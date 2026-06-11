"""Detailed inspection of objects that share the same status as the trailer
in scene-0553_frame8 (already imported into Neo4j).

This is to help reverse-engineer the official "other things of the same status"
semantics (e.g., why official answer is 8 instead of 28).
"""
from neo4j import GraphDatabase

URI = "bolt://localhost:7600"
AUTH = ("neo4j", "87017563")


def main():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        # 1) Trailer basic info
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

        # 2) Aggregated counts by type (same status, excluding trailer itself)
        print("\n[Other objects with same status as trailer (aggregated by type)]")
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

        # 3) Detailed list with distance & direction relative to the trailer
        print("\n[Detailed same-status others: per-object distance & direction from trailer]")
        res = session.run(
            """
            MATCH (t:Object)
            WHERE t.category CONTAINS 'trailer'
            WITH t
            MATCH (t)-[r:RELATES_TO]->(o:Object)
            WHERE o.status = t.status AND o.unique_id <> t.unique_id
            RETURN o.unique_id AS id,
                   o.type AS type,
                   o.status AS status,
                   r.distance AS dist,
                   r.direction_4 AS dir4,
                   r.direction_8 AS dir8
            ORDER BY dist ASC, type, id
            """
        )
        rows = list(res)
        for r in rows:
            print(
                f"  id={r['id']:<8}  type={r['type']:<10}  status={r['status']:<12} "
                f"dist={r['dist']:.2f}m  dir4={r['dir4']:<5}  dir8={r['dir8']}"
            )
        print(f"  TOTAL listed = {len(rows)}")

    driver.close()


if __name__ == "__main__":
    main()
