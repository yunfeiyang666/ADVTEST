"""测试属性提取函数"""
import json
import sys
sys.path.insert(0, r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline')
from import_single_scene_to_neo4j import Neo4jImporter

# 加载场景图
with open(r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0553_frame8_scene_graph.json') as f:
    data = json.load(f)

# 测试第一条边
edge = data['edges'][0]
print('原始edge metrics:')
print(f"  direction_source: {edge['metrics'].get('direction_source')}")
print(f"  direction_ego: {edge['metrics'].get('direction_ego')}")

# 提取属性
props = Neo4jImporter._extract_relationship_properties(edge)
print('\n提取后的props:')
print(f"  angle_matches_source: {props.get('angle_matches_source')}")
print(f"  angle_matches_ego: {props.get('angle_matches_ego')}")
print(f"  direction_8_source: {props.get('direction_8_source')}")
print(f"  direction_8_ego: {props.get('direction_8_ego')}")
