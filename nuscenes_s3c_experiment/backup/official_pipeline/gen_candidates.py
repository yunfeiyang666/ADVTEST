#!/usr/bin/env python3
"""
gen_candidates.py — 生成低密度帧候选的场景图并过滤
检测 scene-0103 frame-0 / frame-1 过滤后节点数是否在 5-8 之间
"""
import os, sys, json, time, pathlib, logging
os.environ["NUSCENES_VERSION"] = "v1.0-trainval"
sys.path.insert(0, str(pathlib.Path(__file__).parent))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

RAW_SG_DIR      = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
DATA_ROOT       = pathlib.Path("E:/Project/ADVTEST/data/nuscenes")
DEVKIT_PATH     = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"

CANDIDATES = [
    ("scene-0103", 0),
    ("scene-0103", 1),
    ("scene-0103", 3),
    ("scene-0103", 15),
    ("scene-0103", 28),
    ("scene-0103", 31),
    ("scene-0103", 33),
]

from core_universe_filter import filter_scene_graph, FILTERED_SG_DIR

def gen_and_filter(scene_name, frame_idx):
    sg_name = f"{scene_name}_frame{frame_idx}_scene_graph.json"
    raw_out = RAW_SG_DIR / sg_name
    flt_out = FILTERED_SG_DIR / sg_name

    if flt_out.exists():
        data = json.loads(flt_out.read_text(encoding="utf-8"))
        info = data.get("core_universe_filter", {})
        return info.get("filtered_nodes", 0), info.get("node_ids_kept", [])

    if not raw_out.exists():
        # Generate
        if DEVKIT_PATH not in sys.path:
            sys.path.insert(0, DEVKIT_PATH)
        from nuscenes.nuscenes import NuScenes
        from generate_selected_scenes_improved import SceneGraphGenerator, SceneGraphConfig
        import config as cfg_mod

        print(f"  Generating {scene_name} frame-{frame_idx}...")
        t0 = time.perf_counter()
        nusc = NuScenes(version="v1.0-trainval", dataroot=str(DATA_ROOT), verbose=False)
        cfg = SceneGraphConfig(
            nuscenes_version="v1.0-trainval",
            nuscenes_dataroot=str(DATA_ROOT),
            output_dir=str(pathlib.Path(__file__).parent / "output"),
            devkit_path=DEVKIT_PATH,
            near_distance=cfg_mod.NEAR_DISTANCE,
            mid_distance=cfg_mod.MID_DISTANCE,
            max_relationship_distance=cfg_mod.MAX_REL_DISTANCE,
        )
        gen = SceneGraphGenerator(nusc, cfg)
        sg_data = gen.generate(scene_name, frame_idx)
        if not sg_data:
            print(f"  ❌ Generation failed for {scene_name} frame-{frame_idx}")
            return -1, []
        RAW_SG_DIR.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(json.dumps(sg_data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        elapsed = time.perf_counter() - t0
        print(f"  ✅ Generated in {elapsed:.1f}s: {sg_data['statistics']}")
        del nusc  # free memory

    # Filter
    raw_data = json.loads(raw_out.read_text(encoding="utf-8"))
    filtered = filter_scene_graph(raw_data)
    flt_out.write_text(json.dumps(filtered, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    info = filtered["core_universe_filter"]
    return info["filtered_nodes"], info["node_ids_kept"]


# ── Main ───────────────────────────────────────────────────────────────────────
print("=" * 65)
print("  Low-density frame scan")
print("=" * 65)

import collections, json
TRAINVAL = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")
QA_PATH  = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json")

scenes  = json.loads((TRAINVAL/"scene.json").read_text())
samples = json.loads((TRAINVAL/"sample.json").read_text())
scene_token2name = {s["token"]: s["name"] for s in scenes}
sample2info = {}
scene2samples = collections.defaultdict(list)
for samp in samples:
    sname = scene_token2name.get(samp["scene_token"],"?")
    sample2info[samp["token"]] = {"scene_name": sname, "timestamp": samp["timestamp"]}
    scene2samples[sname].append(samp["token"])
for sname, toks in scene2samples.items():
    for idx, tok in enumerate(sorted(toks, key=lambda t: sample2info[t]["timestamp"])):
        sample2info[tok]["frame_idx"] = idx

val_qs = json.loads(QA_PATH.read_text())["questions"]
frame_qa = collections.defaultdict(list)
for q in val_qs:
    info = sample2info.get(q.get("sample_token",""), {})
    frame_qa[(info.get("scene_name","?"), info.get("frame_idx",-1))].append(q)

print(f"\n{'Scene:Frame':<30} {'val_qa':>7} {'filtered_nodes':>14}  {'node_ids'}")
print("─" * 90)

best_candidates = []
for scene_name, fidx in CANDIDATES:
    n_qa = len(frame_qa.get((scene_name, fidx), []))
    n_nodes, node_ids = gen_and_filter(scene_name, fidx)
    tag = ""
    if 5 <= n_nodes <= 8 and 5 <= n_qa <= 12:
        tag = "  ⭐ BEST FIT"
        best_candidates.append((scene_name, fidx, n_qa, n_nodes, node_ids))
    elif n_nodes <= 8:
        tag = "  ✅ nodes OK"
    elif n_qa <= 10:
        tag = "  ⚠ QA OK, nodes too many"
    print(f"  {scene_name} frame-{fidx:<3} {n_qa:>7} {n_nodes:>14}  {node_ids[:8]}{tag}")

print("\n" + "=" * 65)
if best_candidates:
    print(f"  ⭐ RECOMMENDED CANDIDATES ({len(best_candidates)}):")
    for sn, fi, nqa, nn, ids in best_candidates:
        print(f"\n  scene_id  : {sn}")
        print(f"  frame_idx : {fi}")
        print(f"  val_qa    : {nqa} 条")
        print(f"  filtered nodes: {nn}")
        print(f"  node_ids  : {ids}")
        print(f"  filtered SG: {FILTERED_SG_DIR / f'{sn}_frame{fi}_scene_graph.json'}")
else:
    print("  No perfect fit. Best options:")
    all_results = [(sn,fi, len(frame_qa.get((sn,fi),[])),
                    gen_and_filter(sn,fi)[0]) for sn,fi in CANDIDATES]
    for sn,fi,nqa,nn in sorted(all_results, key=lambda x: abs(x[3]-6)):
        print(f"  {sn} frame-{fi}: nodes={nn} qa={nqa}")

print("=" * 65)
print("  ⚠ 等待用户 GO 指令后方可开始审计或生成")
