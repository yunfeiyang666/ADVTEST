#!/usr/bin/env python3
"""
准备并运行两帧测试
1. 检查场景图文件是否存在
2. 导入场景图到Neo4j
3. 运行两帧测试
"""
import sys
import json
from pathlib import Path
from neo4j import GraphDatabase

# 添加 official_pipeline 到路径
OFFICIAL_PIPELINE_DIR = Path(__file__).parent / "official_pipeline"
sys.path.insert(0, str(OFFICIAL_PIPELINE_DIR))

def check_scene_graph_files():
    """检查场景图文件是否存在"""
    print("="*80)
    print("检查场景图文件")
    print("="*80)

    # 可能的场景图目录
    possible_dirs = [
        Path(r"E:\Project\ADVTEST\filtered_scene_graphs"),
        Path(r"E:\Project\ADVTEST\filtered_scene_graphs_official"),
        Path(r"E:\Project\ADVTEST\DATA_new\filtered_scene_graphs"),
    ]

    scene_graphs = {}

    for scene_name, frame_idx in [("scene-0916", 8), ("scene-0916", 10)]:
        filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
        found = False

        for dir_path in possible_dirs:
            file_path = dir_path / filename
            if file_path.exists():
                print(f"✓ 找到: {file_path}")
                scene_graphs[f"{scene_name}_frame{frame_idx}"] = file_path
                found = True
                break

        if not found:
            print(f"✗ 未找到: {filename}")
            print(f"  搜索目录:")
            for d in possible_dirs:
                print(f"    - {d}")

    return scene_graphs

def import_scene_to_neo4j(scene_graph_path: Path, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """导入场景图到Neo4j"""
    print(f"\n导入场景图: {scene_graph_path.name}")

    # 加载场景图
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)

    scene_name = scene_graph.get('scene_name', 'unknown')
    frame_idx = scene_graph.get('frame_idx', 0)

    # 兼容两种格式：nodes/edges 或 objects/relationships
    objects = scene_graph.get('objects') or scene_graph.get('nodes', [])
    relationships = scene_graph.get('relationships') or scene_graph.get('edges', [])

    print(f"  场景: {scene_name}, 帧: {frame_idx}")
    print(f"  对象数: {len(objects)}")
    print(f"  关系数: {len(relationships)}")

    # 连接Neo4j
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        with driver.session() as session:
            # 创建节点
            for obj in objects:
                props = {
                    'unique_id': obj['unique_id'],
                    'type': obj['type'],
                    'scene_name': scene_name,
                    'frame_idx': frame_idx
                }

                # 添加可选属性
                if 'status' in obj:
                    props['status'] = obj['status']
                if 'category' in obj:
                    props['category'] = obj['category']

                session.run(
                    """
                    MERGE (obj:Object {unique_id: $unique_id, scene_name: $scene_name, frame_idx: $frame_idx})
                    SET obj = $props
                    """,
                    unique_id=obj['unique_id'],
                    scene_name=scene_name,
                    frame_idx=frame_idx,
                    props=props
                )

            print(f"  ✓ 已创建 {len(objects)} 个节点")

            # 创建关系
            for rel in relationships:
                rel_props = {}

                # 提取关系属性
                if 'metrics' in rel:
                    metrics = rel['metrics']
                    if 'distance' in metrics:
                        rel_props['distance'] = metrics['distance']
                    if 'direction_source' in metrics and isinstance(metrics['direction_source'], dict):
                        if 'direction_8' in metrics['direction_source']:
                            rel_props['direction_8'] = metrics['direction_source']['direction_8']
                        if 'direction_4' in metrics['direction_source']:
                            rel_props['direction_4'] = metrics['direction_source']['direction_4']

                # 兼容旧格式：直接在关系上的属性
                if 'direction_8' in rel:
                    rel_props['direction_8'] = rel['direction_8']
                if 'direction_4' in rel:
                    rel_props['direction_4'] = rel['direction_4']
                if 'direction' in rel:  # 新格式可能用 direction
                    rel_props['direction'] = rel['direction']
                if 'predicates' in rel:
                    rel_props['predicates'] = rel['predicates']
                if 'distance' in rel:
                    rel_props['distance'] = rel['distance']

                # 获取source和target（兼容不同字段名）
                source = rel.get('source') or rel.get('src') or rel.get('from')
                target = rel.get('target') or rel.get('tgt') or rel.get('to')

                session.run(
                    """
                    MATCH (a:Object {unique_id: $source, scene_name: $scene_name, frame_idx: $frame_idx})
                    MATCH (b:Object {unique_id: $target, scene_name: $scene_name, frame_idx: $frame_idx})
                    MERGE (a)-[r:RELATES_TO]->(b)
                    SET r = $props
                    """,
                    source=source,
                    target=target,
                    scene_name=scene_name,
                    frame_idx=frame_idx,
                    props=rel_props
                )

            print(f"  ✓ 已创建 {len(relationships)} 条关系")

    finally:
        driver.close()

    print(f"✓ 场景图导入完成")

def main():
    print("="*80)
    print("准备并运行两帧测试")
    print("="*80)
    print()

    # 1. 检查场景图文件
    scene_graphs = check_scene_graph_files()

    if len(scene_graphs) < 1:
        print()
        print("✗ 未找到场景图文件")
        print()
        print("需要的文件:")
        print("  - scene-0916_frame8_scene_graph.json")
        print("  - scene-0916_frame10_scene_graph.json")
        print()
        print("请先生成场景图文件")
        return 1

    # 2. 检查Neo4j连接
    print()
    print("="*80)
    print("检查Neo4j连接")
    print("="*80)

    passwords = ["87017563", "neo4j", "password"]
    connected = False
    working_password = None

    for pwd in passwords:
        try:
            driver = GraphDatabase.driver(
                "bolt://127.0.0.1:7687",
                auth=("neo4j", pwd)
            )
            driver.verify_connectivity()
            print(f"✓ Neo4j连接成功 (密码: {pwd})")
            working_password = pwd
            driver.close()
            connected = True
            break
        except Exception as e:
            continue

    if not connected:
        print("✗ Neo4j连接失败")
        print()
        print("请确保:")
        print("  1. Neo4j已启动")
        print("  2. 端口7687可访问")
        print("  3. 密码正确")
        return 1

    # 3. 清空数据库
    print()
    print("="*80)
    print("清空Neo4j数据库")
    print("="*80)

    driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", working_password))
    try:
        with driver.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted")
            deleted = result.single()['deleted']
            print(f"✓ 已删除 {deleted} 个节点")
    finally:
        driver.close()

    # 4. 导入场景图
    print()
    print("="*80)
    print("导入场景图到Neo4j")
    print("="*80)

    for key, path in sorted(scene_graphs.items()):
        import_scene_to_neo4j(path, "bolt://127.0.0.1:7687", "neo4j", working_password)

    # 5. 运行测试
    print()
    print("="*80)
    print("运行测试")
    print("="*80)
    print()

    if len(scene_graphs) == 1:
        print("只找到1个场景图文件，将只运行单帧测试")

    from run_two_frames_v6 import run_frame

    for key in sorted(scene_graphs.keys()):
        scene_name, frame_part = key.rsplit('_', 1)
        frame_idx = int(frame_part.replace('frame', ''))

        try:
            result = run_frame(scene_name, frame_idx, working_password=working_password)
            print(f"\n✓ {scene_name} frame {frame_idx} 完成")
            print(f"  生成问题数: {result.get('total_qa', 0)}")
        except Exception as e:
            print(f"\n✗ {scene_name} frame {frame_idx} 失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print()
    print("="*80)
    print("测试完成!")
    print("="*80)
    print()
    print("输出文件在 output/ 目录")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
