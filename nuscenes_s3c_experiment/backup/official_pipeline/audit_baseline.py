#!/usr/bin/env python3
"""
audit_baseline.py — NuScenes-QA 基准数据审计脚本
断点 1：汇报可用帧列表，等待用户选择
"""
import json, sys, collections, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

TRAINVAL_DIR = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")
MINI_DIR     = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-mini")
QA_DIR       = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/qa")
SG_DIR       = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")

print("=" * 65)
print("  ADVTEST Baseline Audit — 断点 1")
print("=" * 65)

# ── Step 1: Load metadata ──────────────────────────────────────────────────
print("\n[1] Loading NuScenes metadata (trainval)...")
scenes  = json.loads((TRAINVAL_DIR / "scene.json").read_text(encoding="utf-8"))
samples = json.loads((TRAINVAL_DIR / "sample.json").read_text(encoding="utf-8"))

scene_token2info = {s["token"]: s for s in scenes}
sample2scene: dict = {}
scene2samples: dict = collections.defaultdict(list)

for i, samp in enumerate(samples):
    si = scene_token2info.get(samp["scene_token"], {})
    sname = si.get("name", "?")
    entry = {
        "sample_token": samp["token"],
        "scene_name":   sname,
        "scene_token":  samp["scene_token"],
        "frame_idx":    -1,   # filled below
        "timestamp":    samp["timestamp"],
    }
    sample2scene[samp["token"]] = entry
    scene2samples[sname].append(samp["token"])

# Assign frame_idx (position within scene, 0-based)
for sname, toks in scene2samples.items():
    # Sort by timestamp
    sorted_toks = sorted(toks, key=lambda t: sample2scene[t]["timestamp"])
    for idx, tok in enumerate(sorted_toks):
        sample2scene[tok]["frame_idx"] = idx

print(f"  Total scenes: {len(scenes)}  Total samples: {len(samples)}")

# ── Step 2: Check Neo4j ─────────────────────────────────────────────────────
print("\n[2] Checking Neo4j database...")
try:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://localhost:7800", auth=("neo4j", "87017563"))
    with driver.session() as s:
        edge_count  = s.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n").single()["n"]
        node_count  = s.run("MATCH (n:Object) RETURN count(n) AS n").single()["n"]
        ego_check   = s.run("MATCH (n:Object {unique_id:'ego'}) RETURN n.unique_id AS id").single()
    driver.close()
    neo4j_ok = True
    print(f"  ✅ Neo4j reachable: {node_count} nodes, {edge_count} edges")
    print(f"     ego node: {'found' if ego_check else 'NOT found'}")
    print(f"     (Currently loaded: scene-0553 frame-8 — 4,032 edges)")
except Exception as exc:
    neo4j_ok = False
    print(f"  ❌ Neo4j error: {exc}")

# ── Step 3: Our scene_graphs ────────────────────────────────────────────────
print("\n[3] Our generated scene_graph files:")
our_files = sorted(SG_DIR.glob("*_scene_graph.json")) if SG_DIR.exists() else []
our_scenes = []
for f in our_files:
    stem = f.stem.replace("_scene_graph", "")
    # stem format: scene-XXXX_frameYY
    parts = stem.rsplit("_frame", 1)
    sname = parts[0] if parts else stem
    fidx  = int(parts[1]) if len(parts) > 1 else -1
    size_kb = f.stat().st_size // 1024
    our_scenes.append({"scene_name": sname, "frame_idx": fidx, "file": f.name, "size_kb": size_kb})
    print(f"  {f.name:<55} {size_kb:>5} KB")

if not our_files:
    print("  (none found — searching broader path)")
    for sg in pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment").rglob("*_scene_graph.json"):
        print(f"    {sg}")

# ── Step 4: Match val questions to our scenes ───────────────────────────────
print("\n[4] Matching NuScenes-QA val set to our scenes...")
val_qs = json.loads((QA_DIR / "NuScenes_val_questions.json").read_text(encoding="utf-8"))["questions"]
print(f"  Val questions total: {len(val_qs)}")

# Per-scene QA stats
scene_qa: dict = collections.defaultdict(lambda: {"total": 0, "by_type": collections.Counter(), "by_hop": collections.Counter()})
for q in val_qs:
    info = sample2scene.get(q.get("sample_token", ""), {})
    sname = info.get("scene_name", "unknown")
    scene_qa[sname]["total"] += 1
    scene_qa[sname]["by_type"][q.get("template_type", "?")] += 1
    scene_qa[sname]["by_hop"][q.get("num_hop", "?")] += 1

print(f"  Val scenes with QA: {len(scene_qa)}")

# ── Step 5: Report our scenes ───────────────────────────────────────────────
print("\n[5] Coverage status for our generated scenes:")
print(f"  {'Scene + Frame':<35} {'Val QA':>7} {'Nodes':>7} {'Status'}")
print("  " + "─" * 65)

for sc in our_scenes:
    sn = sc["scene_name"]
    fi = sc["frame_idx"]
    qa_cnt = scene_qa.get(sn, {}).get("total", 0)
    # Check if NuScenes-trainval has this scene
    in_tv = sn in {s["name"] for s in scenes}
    status = "✅ in trainval" if in_tv else "⚠️ not in trainval"
    print(f"  {sn}_frame{fi:<15} {qa_cnt:>7}  {sc['size_kb']:>5}KB  {status}")

# ── Step 6: Top candidate frames to choose from ─────────────────────────────
print("\n[6] Top 10 candidate frames in val set (most QA questions):")
print(f"  {'Rank':<5} {'Scene Name':<30} {'Val QA':>7} {'Frames':>7} {'Q_types'}")
print("  " + "─" * 65)

# Group by scene, pick best frame
scene_totals = sorted(
    [(sn, info["total"]) for sn, info in scene_qa.items() if sn != "unknown"],
    key=lambda x: -x[1]
)[:20]

displayed = 0
for rank, (sname, total) in enumerate(scene_totals, 1):
    if displayed >= 10:
        break
    n_frames = len(scene2samples.get(sname, []))
    types = scene_qa[sname]["by_type"]
    top_types = ", ".join(f"{t}:{c}" for t, c in types.most_common(3))
    in_our = sname in {sc["scene_name"] for sc in our_scenes}
    tag = " ◄ already have SG" if in_our else ""
    print(f"  {rank:<5} {sname:<30} {total:>7} {n_frames:>7}  [{top_types}]{tag}")
    displayed += 1

# ── Step 7: Save mapping for downstream use ──────────────────────────────────
out = pathlib.Path("output/audit_baseline_result.json")
out.parent.mkdir(parents=True, exist_ok=True)
result = {
    "total_val_questions": len(val_qs),
    "total_scenes_in_val": len(scene_qa),
    "our_scenes": our_scenes,
    "top10_candidates": [
        {
            "rank": i+1,
            "scene_name": sn,
            "val_qa_count": cnt,
            "n_frames": len(scene2samples.get(sn, [])),
            "qa_by_type": dict(scene_qa[sn]["by_type"]),
            "qa_by_hop":  dict(scene_qa[sn]["by_hop"]),
        }
        for i, (sn, cnt) in enumerate(scene_totals[:10])
    ],
    "sample_to_scene_map_size": len(sample2scene),
}
out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n[7] Audit result saved → {out}")

print("\n" + "=" * 65)
print("  ✅ 断点 1 完成 — 请选择目标帧，然后发送 GO")
print("=" * 65)
