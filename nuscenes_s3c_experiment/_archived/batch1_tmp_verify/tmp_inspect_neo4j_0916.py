from vqa_pipeline.neo4j_client import Neo4jClient

client = Neo4jClient()
if not client.connect():
    raise SystemExit("Neo4j connect failed")

print("Edges from ego (predicates[0], target):")
res_ego = client.execute_query(
    "MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(t:Object) "
    "RETURN t.unique_id AS tid, t.type AS ttype, r.predicates[0] AS dir ORDER BY tid LIMIT 100"
)
for row in res_ego.get("data", []):
    print(row)

print("\nEdges from bus (type='bus'):")
res_bus = client.execute_query(
    "MATCH (b:Object {type:'bus'})-[r:RELATES_TO]->(t:Object) "
    "RETURN b.unique_id AS bid, t.unique_id AS tid, t.type AS ttype, r.predicates[0] AS dir ORDER BY tid LIMIT 100"
)
for row in res_bus.get("data", []):
    print(row)

client.close()
