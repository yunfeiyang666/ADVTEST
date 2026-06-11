"""
检查 translation 格式问题
"""
import json

with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r') as f:
    sg = json.load(f)

# 检查节点中translation的格式
print("=== 场景图 JSON 中 translation 的格式 ===")
for node in sg['nodes'][:3]:
    print(f"{node['unique_id']}: {node['translation']}, type={type(node['translation'])}")

print("\n=== 问题分析 ===")
print("场景图JSON中，translation已经是dict格式: {'x': ..., 'y': ..., 'z': ...}")
print()
print("但 compute_direction_features 中:")
print("  src = np.array(list(source_translation), dtype=float)")
print("  这会尝试对dict调用list()!")
print()
print("测试 list(dict) 的结果:")
test_trans = {'x': 688.33, 'y': 1575.98, 'z': 0.0}
print(f"  test_trans = {test_trans}")
print(f"  list(test_trans) = {list(test_trans)}")
print(f"  这只会返回keys: ['x', 'y', 'z']，不是数值!")
print()
print("❌ 找到BUG了！")
print("当translation是dict时，list(translation)只返回keys，不是坐标值")
print("np.array(['x', 'y', 'z']) 会导致类型错误或随机行为")
