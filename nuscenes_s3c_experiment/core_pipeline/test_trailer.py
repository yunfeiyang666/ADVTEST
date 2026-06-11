"""测试trailer查询"""
from neo4j import GraphDatabase

d = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
s = d.session()

print('Test 1: category CONTAINS trailer')
r = s.run("MATCH (n:Object) WHERE n.category CONTAINS 'trailer' RETURN count(n) as cnt")
print('  Result:', r.single()['cnt'])

print('\nTest 2: Are there any trailers?')
r = s.run("MATCH (n:Object) WHERE n.category CONTAINS 'trailer' RETURN count(n) > 0 AS result")
print('  Result:', r.single()['result'])

print('\nTest 3: How many barriers to front of trailer?')
r = s.run("""
MATCH (trailer:Object) 
WHERE trailer.category CONTAINS 'trailer'
WITH trailer LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(barrier:Object)
WHERE barrier.type = 'barrier' AND 'front' IN r.angle_matches_source
RETURN count(barrier) AS count
""")
print('  Result:', r.single()['count'])

print('\nTest 4: Trailer status')
r = s.run("MATCH (n:Object) WHERE n.category CONTAINS 'trailer' RETURN n.status")
print('  Result:', r.single()['n.status'])

d.close()
