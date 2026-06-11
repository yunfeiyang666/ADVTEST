#!/usr/bin/env python3
"""
gen_scene0926.py — 生成 scene-0926 frame-20 场景图并导入 Neo4j
直接调用 SceneGraphGenerator，绕过 selected_scenes.json 依赖
使用 v1.0-trainval 版本（非 mini）
"""
import os, sys, json, time, pathlib, logging

# ── 强制使用 trainval ──────────────────────────────────────────────────────────
os.environ["NUSCENES_VERSION"] = "v1.0-trainval"
sys.path.insert(0, str(pathlib.Path(__file__).parent))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SG_DIR = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
DATA_ROOT = pathlib.Path("E:/Project/ADVTEST/data/nuscenes")
DEVKIT_PATH = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
TARGET_SCENE = "scene-0926"
TARGET_FRAME = 20
sg_out = SG_DIR / f"{TARGET_SCENE}_frame{TARGET_FRAME}_scene_graph.json"

print("=" * 60)
print(f"  生成 {TARGET_SCENE} frame-{TARGET_FRAME} 场景图")
print("=" * 60)

if sg_out.exists():
    print(f"  ✅ 已存在 ({sg_out.stat().st_size//1024} KB) — 跳过生成")
else:
    # ── Setup devkit path ─────────────────────────────────────────────────────
    if DEVKIT_PATH not in sys.path:
        sys.path.insert(0, DEVKIT_PATH)

    from nuscenes.nuscenes import NuScenes
    from generate_selected_scenes_improved import (
        SceneGraphGenerator, SceneGraphConfig
    )
    import config as core_config

    t0 = time.perf_counter()
    logger.info("加载 NuScenes v1.0-trainval...")
    nusc = NuScenes(version="v1.0-trainval", dataroot=str(DATA_ROOT), verbose=False)
    logger.info(f"  ✅ 已加载 {len(nusc.scene)} 个场景")

    # Build config manually (override version)
    cfg = SceneGraphConfig(
        nuscenes_version="v1.0-trainval",
        nuscenes_dataroot=str(DATA_ROOT),
        output_dir=str(pathlib.Path(__file__).parent / "output"),
        devkit_path=DEVKIT_PATH,
        near_distance=core_config.NEAR_DISTANCE,
        mid_distance=core_config.MID_DISTANCE,
        max_relationship_distance=core_config.MAX_REL_DISTANCE,
    )

    generator = SceneGraphGenerator(nusc, cfg)
    logger.info(f"  正在生成 {TARGET_SCENE} frame-{TARGET_FRAME}...")
    sg_data = generator.generate(TARGET_SCENE, TARGET_FRAME)

    if not sg_data:
        print(f"  ❌ 生成失败！")
        sys.exit(1)

    SG_DIR.mkdir(parents=True, exist_ok=True)
    sg_out.write_text(json.dumps(sg_data, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    elapsed = time.perf_counter() - t0
    size_kb = sg_out.stat().st_size // 1024
    stats = sg_data["statistics"]
    print(f"\n  ✅ 场景图生成完成 ({elapsed:.1f}s)")
    print(f"     路径     : {sg_out}")
    print(f"     大小     : {size_kb} KB")
    print(f"     对象数   : {stats['total_objects']}")
    print(f"     关系数   : {stats['total_relationships']}")
    print(f"     类型分布 : {stats['object_type_count']}")

# ── Neo4j 导入 ────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  导入 Neo4j (bolt://localhost:7800)")
print("=" * 60)

from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7800",
                               auth=("neo4j", "87017563"))

# Read the import script to find the correct function
import_script = pathlib.Path("import_single_scene_to_neo4j.py")
src = import_script.read_text(encoding="utf-8", errors="ignore")

# The import_single_scene_to_neo4j.py may have a main function we can call
# Let's parse the scene graph and import directly
sg_data = json.loads(sg_out.read_text(encoding="utf-8"))

print(f"  Scene graph loaded: {len(sg_data['nodes'])} nodes, {len(sg_data['edges'])} edges")

# Perform import
with driver.session() as session:
    # Clear existing data
    session.run("MATCH (n) DETACH DELETE n")
    print("  Cleared existing Neo4j data")

    # Import nodes
    n_nodes = 0
    for node in sg_data["nodes"]:
        session.run("""
            CREATE (n:Object {
                unique_id: $uid, type: $type, status: $status
            })
        """, uid=node["unique_id"], type=node["type"],
             status=node.get("status", ""))
        n_nodes += 1
    print(f"  Imported {n_nodes} nodes")

    # Import edges with all attributes
    n_edges = 0
    for edge in sg_data["edges"]:
        metrics = edge.get("metrics", {})
        predicates = edge.get("predicates", [])
        session.run("""
            MATCH (s:Object {unique_id: $src})
            MATCH (t:Object {unique_id: $tgt})
            CREATE (s)-[r:RELATES_TO {
                direction_4: $dir4,
                direction_8: $dir8,
                predicates:  $predicates,
                distance:    $distance
            }]->(t)
        """,
        src=edge["source"],
        tgt=edge["target"],
        dir4=edge.get("direction_4", ""),
        dir8=edge.get("direction_8", ""),
        predicates=predicates,
        distance=metrics.get("distance", 0.0))
        n_edges += 1
    print(f"  Imported {n_edges} edges")

    # Create indexes
    try:
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Object) ON (n.unique_id)")
        print("  Index created on Object.unique_id")
    except Exception:
        pass

    # Verify
    result = session.run("MATCH (n:Object) RETURN count(n) AS c").single()
    n_verify = result["c"]
    result2 = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c").single()
    e_verify = result2["c"]
    print(f"\n  ✅ Verification: {n_verify} nodes, {e_verify} edges in Neo4j")

driver.close()

print(f"\n{'='*60}")
print(f"  ✅ scene-0926 frame-20 已就绪")
print(f"  节点: {n_verify}  边: {e_verify}")
print(f"  场景图: {sg_out.name}")
print(f"{'='*60}")
