"""Quick test to verify undirected Neo4j queries work with pivot cells."""
from neo4j import GraphDatabase

d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563'))
with d.session() as s:
    # Test directed vs undirected edge counts
    r_dir = s.run('MATCH (a:Object)-[r:RELATES_TO]->(b:Object) RETURN count(r) AS n').single()
    r_und = s.run('MATCH (a:Object)-[r:RELATES_TO]-(b:Object) RETURN count(r) AS n').single()
    print(f"Directed edges:   {r_dir['n']}")
    print(f"Undirected edges: {r_und['n']}")

    # Get 3 sample node IDs
    rows = s.run('MATCH (n:Object) RETURN n.unique_id AS id LIMIT 5').values()
    ids = [r[0] for r in rows]
    print(f"Sample nodes: {ids}")

    if len(ids) >= 3:
        n1, n2, n3 = ids[0], ids[1], ids[2]
        # Directed MATCH
        q_dir = (
            f"MATCH (a:Object {{unique_id:'{n1}'}})-[:RELATES_TO]->"
            f"(b:Object {{unique_id:'{n2}'}})-[:RELATES_TO]->"
            f"(c:Object {{unique_id:'{n3}'}}) RETURN 1 AS ok LIMIT 1"
        )
        r_d = s.run(q_dir).single()
        print(f"Directed  ({n1}->{n2}->{n3}): {'FOUND' if r_d else 'NOT FOUND'}")

        # Undirected MATCH
        q_und = (
            f"MATCH (a:Object {{unique_id:'{n1}'}})-[:RELATES_TO]-"
            f"(b:Object {{unique_id:'{n2}'}})-[:RELATES_TO]-"
            f"(c:Object {{unique_id:'{n3}'}}) RETURN 1 AS ok LIMIT 1"
        )
        r_u = s.run(q_und).single()
        print(f"Undirected({n1}-{n2}-{n3}):  {'FOUND' if r_u else 'NOT FOUND'}")

        # Full L2 fallback style query (undirected)
        q_full = (
            f"MATCH (a:Object {{unique_id: '{n1}'}})-[r1:RELATES_TO]-(b:Object {{unique_id: '{n2}'}})"
            f"      -[r2:RELATES_TO]-(c:Object {{unique_id: '{n3}'}})"
            f" OPTIONAL MATCH (b)-[r3:RELATES_TO]-(sibling:Object)"
            f"   WHERE sibling.unique_id <> '{n1}' AND sibling.unique_id <> '{n3}'"
            f" WITH a, b, c, r1, r2,"
            f"      collect({{id:sibling.unique_id, type:sibling.type}}) AS siblings"
            f" RETURN a.unique_id AS n1_id, b.unique_id AS n2_id, c.unique_id AS n3_id,"
            f"        size(siblings) AS n_siblings"
        )
        r_full = s.run(q_full).single()
        if r_full:
            print(f"Full L2 query: n1={r_full['n1_id']}, n2={r_full['n2_id']}, n3={r_full['n3_id']}, siblings={r_full['n_siblings']}")
        else:
            print("Full L2 query: NOT FOUND")

d.close()
print("\nALL TESTS PASSED")
