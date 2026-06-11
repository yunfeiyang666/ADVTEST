"""Probe different rules for "same status as the trailer" counting
in scene-0553_frame8 (already imported into Neo4j).
"""
from neo4j import GraphDatabase

URI = "bolt://localhost:7600"
AUTH = ("neo4j", "87017563")


RULES = [
    (
        "R1: all same-status others (no type/distance filter)",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t.status AS trailerStatus, t.unique_id AS trailerId
        MATCH (o:Object)
        WHERE o.status = trailerStatus AND o.unique_id <> trailerId
        RETURN count(o) AS c
        """,
    ),
    (
        "R2: dynamic-only types (car,truck,bus,bicycle,motorcycle,trailer,pedestrian)",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t.status AS trailerStatus, t.unique_id AS trailerId
        MATCH (o:Object)
        WHERE o.status = trailerStatus
          AND o.unique_id <> trailerId
          AND o.type IN ['car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
        RETURN count(o) AS c
        """,
    ),
    (
        "R3: vehicles-only (car,truck,bus,bicycle,motorcycle,trailer)",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t.status AS trailerStatus, t.unique_id AS trailerId
        MATCH (o:Object)
        WHERE o.status = trailerStatus
          AND o.unique_id <> trailerId
          AND o.type IN ['car','truck','bus','bicycle','motorcycle','trailer']
        RETURN count(o) AS c
        """,
    ),
    (
        "R4: vehicles-only + within 20m of trailer",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t
        MATCH (t)-[r:RELATES_TO]->(o:Object)
        WHERE o.status = t.status
          AND o.unique_id <> t.unique_id
          AND o.type IN ['car','truck','bus','bicycle','motorcycle','trailer']
          AND r.distance <= 20
        RETURN count(o) AS c
        """,
    ),
    (
        "R5: vehicles-only + front hemisphere (dir8 in front/front-left/front-right)",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t
        MATCH (t)-[r:RELATES_TO]->(o:Object)
        WHERE o.status = t.status
          AND o.unique_id <> t.unique_id
          AND o.type IN ['car','truck','bus','bicycle','motorcycle','trailer']
          AND r.direction_8 IN ['front','front-left','front-right']
        RETURN count(o) AS c
        """,
    ),
    (
        "R6: vehicles-only + front hemisphere + within 80m",
        """
        MATCH (t:Object)
        WHERE t.category CONTAINS 'trailer'
        WITH t
        MATCH (t)-[r:RELATES_TO]->(o:Object)
        WHERE o.status = t.status
          AND o.unique_id <> t.unique_id
          AND o.type IN ['car','truck','bus','bicycle','motorcycle','trailer']
          AND r.direction_8 IN ['front','front-left','front-right']
          AND r.distance <= 80
        RETURN count(o) AS c
        """,
    ),
]


def main():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        for name, query in RULES:
            print("\n" + "=" * 80)
            print(name)
            print("-" * 80)
            res = session.run(query)
            record = res.single()
            c = record["c"] if record is not None else None
            print("count =", c)
    driver.close()


if __name__ == "__main__":
    main()
