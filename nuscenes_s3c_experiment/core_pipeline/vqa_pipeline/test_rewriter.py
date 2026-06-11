"""Comprehensive test for CypherCoverageRewriter"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from vqa_pipeline.cypher_coverage_rewriter import CypherCoverageRewriter

r = CypherCoverageRewriter()
passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1

# ===== Test 1: Simple 1-hop query =====
print("=== Test 1: 1-hop query ===")
cypher1 = (
    "MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj:Object) "
    "WHERE obj.status='stopped' AND 'back' IN r.angle_matches_source "
    "RETURN obj.type LIMIT 1"
)
rw1 = r.rewrite(cypher1)
print(f"  Rewritten: {rw1}")
check("contains _cov_0_id (ego)", "ego.unique_id AS _cov_0_id" in rw1)
check("contains _cov_1_dir (r)", "r.direction_8_ego AS _cov_1_dir" in rw1)
check("contains _cov_2_id (obj)", "obj.unique_id AS _cov_2_id" in rw1)
check("LIMIT preserved", rw1.strip().endswith("LIMIT 1"))
print()

# ===== Test 2: Count/aggregation query =====
print("=== Test 2: Aggregation query ===")
cypher2 = "MATCH (c:Object {type:'car'}) WHERE c.status='stopped' RETURN count(c) AS count"
rw2 = r.rewrite(cypher2)
print(f"  Rewritten: {rw2}")
check("uses collect(DISTINCT ...)", "collect(DISTINCT c.unique_id)" in rw2)
check("original answer preserved", "count(c) AS count" in rw2)
print()

# ===== Test 3: 2-hop query =====
print("=== Test 3: 2-hop query ===")
cypher3 = (
    "MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(mid:Object)"
    "-[r2:RELATES_TO]->(tgt:Object) "
    "WHERE 'front' IN r1.angle_matches_source "
    "RETURN tgt.status LIMIT 1"
)
rw3 = r.rewrite(cypher3)
print(f"  Rewritten: {rw3}")
check("interleaved: ego(0), r1(1), mid(2), r2(3), tgt(4)",
      "_cov_0_id" in rw3 and "_cov_1_dir" in rw3 and
      "_cov_2_id" in rw3 and "_cov_3_dir" in rw3 and "_cov_4_id" in rw3)
print()

# ===== Test 4: Node-only query (no relationship) =====
print("=== Test 4: Node-only query ===")
cypher4 = "MATCH (n:Object) WHERE n.status='with_rider' RETURN n.type LIMIT 1"
rw4 = r.rewrite(cypher4)
print(f"  Rewritten: {rw4}")
check("contains node id", "n.unique_id AS _cov_0_id" in rw4)
check("no direction field", "_dir" not in rw4)
print()

# ===== Test 5: Coverage extraction — 1-hop =====
print("=== Test 5: Coverage extraction (1-hop) ===")
mock1 = {
    "success": True,
    "data": [{
        "obj.type": "car",
        "_cov_0_id": "ego",
        "_cov_1_dir": "back",
        "_cov_2_id": "car1",
    }]
}
cov1 = r.extract_coverage_from_result(mock1)
print(f"  Nodes: {cov1.covered_nodes}")
print(f"  Edges: {cov1.covered_edges}")
check("2 nodes", cov1.covered_nodes == {"ego", "car1"})
check("1 edge (ego,back,car1)", ("ego", "back", "car1") in cov1.covered_edges)
print()

# ===== Test 6: Coverage extraction — 2-hop =====
print("=== Test 6: Coverage extraction (2-hop) ===")
mock2 = {
    "success": True,
    "data": [{
        "tgt.status": "stopped",
        "_cov_0_id": "ego",
        "_cov_1_dir": "front",
        "_cov_2_id": "car1",
        "_cov_3_dir": "left",
        "_cov_4_id": "ped1",
    }]
}
cov2 = r.extract_coverage_from_result(mock2)
print(f"  Nodes: {cov2.covered_nodes}")
print(f"  Edges: {cov2.covered_edges}")
print(f"  2-hop: {cov2.covered_2hop}")
check("3 nodes", cov2.covered_nodes == {"ego", "car1", "ped1"})
check("2 edges", len(cov2.covered_edges) == 2)
check("edge1 (ego,front,car1)", ("ego", "front", "car1") in cov2.covered_edges)
check("edge2 (car1,left,ped1)", ("car1", "left", "ped1") in cov2.covered_edges)
check("1 2-hop path", ("ego", "car1", "ped1") in cov2.covered_2hop)
print()

# ===== Test 7: Empty/null graceful handling =====
print("=== Test 7: Edge cases ===")
check("empty string", r.rewrite("") == "")
check("None input", r.rewrite(None) is None)
cov_empty = r.extract_coverage_from_result(None)
check("empty result", len(cov_empty.covered_nodes) == 0)
print()

# ===== Test 8: WITH clause query =====
print("=== Test 8: WITH clause ===")
cypher8 = (
    "MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer' "
    "WITH truck.status AS refStatus, truck.unique_id AS refId LIMIT 1 "
    "MATCH (other:Object) WHERE other.status=refStatus AND other.unique_id<>refId "
    "RETURN count(other) AS count"
)
rw8 = r.rewrite(cypher8)
print(f"  Rewritten: {rw8}")
check("aggregation detected", "collect(DISTINCT" in rw8)
print()

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("All tests passed!")
else:
    print(f"WARNING: {failed} test(s) failed")
    sys.exit(1)
