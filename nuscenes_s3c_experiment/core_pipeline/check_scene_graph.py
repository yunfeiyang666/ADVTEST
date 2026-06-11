"""检查场景图文件结构"""
import json
import pprint

path = r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json'
data = json.load(open(path, 'r', encoding='utf-8'))

print("顶层键:", list(data.keys()))
print()

# 检查 edges/relationships
edges_key = 'edges' if 'edges' in data else 'relationships'
if edges_key in data:
    print(f"关系数量: {len(data[edges_key])}")
    
    # 查找 motorcycle 作为 source 的关系
    print("\n=== motorcycle 作为 source 的关系 ===")
    moto_edges = [e for e in data[edges_key] if e.get('source_type') == 'motorcycle' or e.get('source', '').startswith('motorcycle')]
    print(f"找到 {len(moto_edges)} 条")
    if moto_edges:
        print("\n第一条 motorcycle 关系:")
        pprint.pprint(moto_edges[0])
    
    # 查找任意关系检查 direction_source
    print("\n=== 检查 direction_source 数据 ===")
    has_dir_source = 0
    no_dir_source = 0
    for e in data[edges_key][:100]:
        metrics = e.get('metrics', {})
        if 'direction_source' in metrics and metrics['direction_source']:
            has_dir_source += 1
        else:
            no_dir_source += 1
    print(f"前100条关系中：有direction_source={has_dir_source}, 无direction_source={no_dir_source}")
else:
    print("没有找到 edges 或 relationships 键")
