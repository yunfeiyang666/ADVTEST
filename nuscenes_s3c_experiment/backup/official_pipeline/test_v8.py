#!/usr/bin/env python3
"""Unit tests for V8 fixes."""
import ast, pathlib, sys
base = pathlib.Path(__file__).parent
sys.path.insert(0, str(base))

# Syntax check
ok = True
for f in ['semantic_auditor.py', 'rq_tables.py', 'run_method_a.py']:
    try:
        ast.parse((base/f).read_text(encoding='utf-8'))
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'ERR {f}: {e}')
        ok = False

if not ok:
    sys.exit(1)

# Unit test: derive_l2_from_l1
from semantic_auditor import derive_l2_from_l1, make_qa_id, _ms_now

# Test 1: Basic chain
l1 = [
    {'source': 'ego',    'target': 'truck1', 'dir': 'front'},
    {'source': 'truck1', 'target': 'car5',   'dir': 'right'},
    {'source': 'ego',    'target': 'car3',   'dir': 'left'},
]
l2 = derive_l2_from_l1(l1)
print(f'\nTest 1 — ego→truck1→car5 chain:')
print(f'  L1={len(l1)} edges → L2={len(l2)} chains: {l2}')
assert len(l2) == 1, f"Expected 1 chain, got {len(l2)}"
assert l2[0] == {'o1': 'ego', 'o2': 'truck1', 'o3': 'car5'}, f"Wrong chain: {l2[0]}"
print('  PASS')

# Test 2: No chains (star pattern)
l1_star = [
    {'source': 'ego', 'target': 'car1', 'dir': 'front'},
    {'source': 'ego', 'target': 'car2', 'dir': 'right'},
    {'source': 'ego', 'target': 'car3', 'dir': 'left'},
]
l2_star = derive_l2_from_l1(l1_star)
print(f'\nTest 2 — star pattern (no L2):')
print(f'  L1={len(l1_star)} edges → L2={len(l2_star)} chains: {l2_star}')
assert len(l2_star) == 0, f"Expected 0 chains (star has no consecutive edges), got {len(l2_star)}"
print('  PASS')

# Test 3: Multiple chains
l1_multi = [
    {'source': 'ego',    'target': 'car1',   'dir': 'front'},
    {'source': 'car1',   'target': 'car2',   'dir': 'front'},
    {'source': 'car1',   'target': 'bike1',  'dir': 'left'},
]
l2_multi = derive_l2_from_l1(l1_multi)
print(f'\nTest 3 — two chains from car1:')
print(f'  L1={len(l1_multi)} edges → L2={len(l2_multi)} chains: {l2_multi}')
assert len(l2_multi) == 2, f"Expected 2 chains, got {len(l2_multi)}"
print('  PASS')

# Test 4: Empty input
assert derive_l2_from_l1([]) == []
print('\nTest 4 — empty L1 → empty L2: PASS')

# Test: make_qa_id
qid = make_qa_id(71051, "comparison")
print(f'\nmake_qa_id(71051, comparison) = {qid}')
assert qid == "val_71051_comparison"
print('PASS')

# Test: ms timestamp format
ts = _ms_now()
print(f'_ms_now() = {ts}')
assert len(ts) == 23 and ts[10] == ' ' and ts[19] == '.', f"Wrong format: {ts}"
print('PASS')

print('\n✅ All V8 unit tests passed!')
