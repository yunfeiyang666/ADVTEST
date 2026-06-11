#!/usr/bin/env python3
"""V8 Diagnosis: val QA fields, filter analysis, Cypher return parsing."""
import json, pathlib, sys, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent))

QA_PATH = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json")
FSG_DIR = pathlib.Path("E:/Project/ADVTEST/filtered_scene_graphs")
RAW_SG  = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
TRAINVAL = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")

print("=" * 65)
print("  V8 Diagnosis")
print("=" * 65)

# ── 1. Val QA field structure ─────────────────────────────────────────────────
print("\n[1] NuScenes_val_questions.json field analysis")
val = json.loads(QA_PATH.read_text())["questions"]
print(f"  Total val questions: {len(val)}")
q0 = val[0]
print(f"  First question ALL fields:")
for k, v in q0.items():
    print(f"    '{k}': {repr(v)[:80]}")

# Check if there's a unique ID field
print(f"\n  Field that could be used as unique ID:")
for k in q0.keys():
    print(f"    '{k}' — sample: {repr(q0[k])[:60]}")

# Check for duplicate sample_tokens in scene-0926 frame-20
scenes  = json.loads((TRAINVAL/"scene.json").read_text())
samples = json.loads((TRAINVAL/"sample.json").read_text())
st2name = {s["token"]: s["name"] for s in scenes}
s2toks = collections.defaultdict(list)
tok2info = {}
for samp in samples:
    sname = st2name.get(samp["scene_token"],"?")
    tok2info[samp["token"]] = {"scene_name": sname, "timestamp": samp["timestamp"]}
    s2toks[sname].append(samp["token"])
for sname, toks in s2toks.items():
    for idx, tok in enumerate(sorted(toks, key=lambda t: tok2info[t]["timestamp"])):
        tok2info[tok]["frame_idx"] = idx

target_qs = [
    (i, q) for i, q in enumerate(val)
    if tok2info.get(q.get("sample_token",""), {}).get("scene_name") == "scene-0926"
    and tok2info.get(q.get("sample_token",""), {}).get("frame_idx") == 20
]
print(f"\n  scene-0926 frame-20 val questions: {len(target_qs)}")
print(f"  Sample tokens (unique?): {len(set(q.get('sample_token','') for _,q in target_qs))} unique tokens")
print(f"  Each question's unique key options:")
for i, (idx, q) in enumerate(target_qs[:5]):
    tok = q.get("sample_token","")
    print(f"    q[{idx}]: sample_token={tok[:12]}...  template={q.get('template_type','')}  "
          f"  => proposed_id: val_s{tok[:8]}_{idx:04d}")

# ── 2. Filter analysis for scene-0926 frame-20 ───────────────────────────────
print("\n[2] Filter analysis: scene-0926 frame-20")
raw_sg_path = RAW_SG / "scene-0926_frame20_scene_graph.json"
flt_sg_path = FSG_DIR / "scene-0926_frame20_scene_graph.json"

if raw_sg_path.exists():
    raw = json.loads(raw_sg_path.read_text(encoding="utf-8"))
    flt = json.loads(flt_sg_path.read_text(encoding="utf-8")) if flt_sg_path.exists() else None
    
    raw_nodes = raw.get("nodes", [])
    flt_info  = flt.get("core_universe_filter", {}) if flt else {}
    kept_ids  = set(flt_info.get("node_ids_kept", []))
    
    # Get ego position
    ego_pos = None
    for n in raw_nodes:
        if n.get("unique_id") == "ego":
            t = n.get("translation", {})
            ego_pos = (t.get("x",0), t.get("y",0)) if isinstance(t, dict) else (t[0],t[1])
            break
    
    import math
    print(f"  Raw node count: {len(raw_nodes)}")
    print(f"  Filtered node count: {len(kept_ids)}")
    print(f"\n  {'unique_id':<20} {'type':<15} {'distance_m':>12} {'kept?':>6} {'reason'}")
    print("  " + "─" * 75)
    
    for n in sorted(raw_nodes, key=lambda x: x.get("unique_id","")):
        uid   = n.get("unique_id","")
        ntype = n.get("type","")
        t     = n.get("translation",{})
        
        if uid == "ego":
            dist = 0.0
        elif ego_pos:
            if isinstance(t, dict):
                dx, dy = t.get("x",0)-ego_pos[0], t.get("y",0)-ego_pos[1]
            elif isinstance(t, list) and len(t) >= 2:
                dx, dy = t[0]-ego_pos[0], t[1]-ego_pos[1]
            else:
                dx, dy = 0, 0
            dist = math.sqrt(dx*dx + dy*dy)
        else:
            dist = -1
        
        CORE_TYPES = {"car","truck","bus","pedestrian","bicycle","motorcycle"}
        kept = uid in kept_ids
        if uid == "ego":
            reason = "ego (always kept)"
        elif ntype not in CORE_TYPES:
            reason = f"NON-CORE type '{ntype}'"
        elif dist > 20.0:
            reason = f"dist {dist:.1f}m > 20m"
        else:
            reason = "kept (core + within 20m)"
        
        tag = "✅" if kept else "❌"
        print(f"  {uid:<20} {ntype:<15} {dist:>11.1f}m {tag:>6}  {reason}")

# ── 3. Simulate audit Cypher parsing ──────────────────────────────────────────
print("\n[3] Audit Cypher return value parsing simulation")
print("  Current parsing code in semantic_auditor.py:")
print("    l0 = list(rec.get('l0_nodes', []) or [])")
print("    l1 = [dict(e) for e in (rec.get('l1_edges', []) or [])]")
print("    l2 = [dict(p) for p in (rec.get('l2_paths', []) or [])]")
print()
print("  Problem: If LLM generates a Cypher that returns different alias names,")
print("  or returns a MAP/LIST in an unexpected format, parsing silently returns [].")
print()
print("  Example bad Cypher the LLM might generate:")
print("    RETURN collect(ego.unique_id, tgt.unique_id) AS l0_nodes  <- ILLEGAL")
print("    RETURN [ego.unique_id, tgt.unique_id] AS l0_nodes          <- OK but no collect")  
print("    RETURN collect(tgt.unique_id) AS l0_nodes                   <- OK but loses ego")

# ── 4. L2 always 0 diagnosis ──────────────────────────────────────────────────
print("\n[4] Why L2 is always 0")
print("  Val questions num_hop distribution for scene-0926 frame-20:")
hop_counts = collections.Counter(q.get("num_hop",0) for _,q in target_qs)
type_counts = collections.Counter(q.get("template_type","") for _,q in target_qs)
for hop, cnt in sorted(hop_counts.items()):
    print(f"    num_hop={hop}: {cnt} questions")
print("  Template types:")
for ttype, cnt in type_counts.most_common():
    print(f"    {ttype:<20}: {cnt}")
print()
print("  Analysis: If most questions are num_hop=1, LLM only returns 1-hop Cypher")
print("  → l2_paths stays empty. Need to force 2-hop MATCH when num_hop >= 2")

print("\n✅ Diagnosis complete")
