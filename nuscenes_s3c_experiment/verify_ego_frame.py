"""
验证 ego frame 方向计算是否正确
"""
import json
import math

# 读取场景图
with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r') as f:
    sg = json.load(f)

# 获取关键对象坐标
ego = truck1 = ped7 = ped8 = None
for node in sg['nodes']:
    if node['unique_id'] == 'ego':
        ego = node
    elif node['unique_id'] == 'truck1':
        truck1 = node
    elif node['unique_id'] == 'pedestrian7':
        ped7 = node
    elif node['unique_id'] == 'pedestrian8':
        ped8 = node

print("=== 坐标数据 ===")
print(f"ego:   x={ego['translation']['x']:.2f}, y={ego['translation']['y']:.2f}")
print(f"truck1: x={truck1['translation']['x']:.2f}, y={truck1['translation']['y']:.2f}")
print(f"ped7:   x={ped7['translation']['x']:.2f}, y={ped7['translation']['y']:.2f}")
print(f"ped8:   x={ped8['translation']['x']:.2f}, y={ped8['translation']['y']:.2f}")

# 从 BEV 图看方向（上北下南，右东左西）
# ego 在 (688.33, 1575.98)
# truck1 在 (695.26, 1581.75) - ego 的右前方
# ped7 在 (640.31, 1606.25) - 从 truck 看，x更小(左/后)，y更大(后)
# ped8 在 (639.03, 1609.72) - 从 truck 看，x更小(左/后)，y更大(后)

print("\n=== 从 BEV 图分析（假设 ego 面向图的某个方向）===")
print("我们需要知道 ego 的朝向（yaw）才能判断 ego frame 下的方向")
print(f"ego rotation: {ego['rotation']}")

# 假设 ego yaw 约等于 -41° (之前计算的)
# 或者根据 ego->ped5 = back-right (-139.6°) 来推断

print("\n=== 场景图中的边数据 ===")
for e in sg['edges']:
    if e['source'] == 'truck1' and e['target'] in ['pedestrian7', 'pedestrian8']:
        print(f"truck1 -> {e['target']}:")
        print(f"  angle={e['metrics']['angle']}°, direction_8={e['direction_8']}")
        print(f"  relative_position: {e['metrics']['relative_position']}")

print("\n=== 检验：ego frame 下 truck1->ped7 应该是什么方向？===")
# 在 ego frame 下：
# - 角度 18.5° 应该是 front (因为 -22.5 ~ 22.5 是 front)
# 但从 BEV 图看，ped7 明显在 truck1 的后方（y 值更大）

print("问题：BEV 图显示 ped7/8 在 truck1 的左上方")
print("如果 ego 面向的是图的右下方，那么从 ego frame 看：")
print("  truck1 左上方 = ego frame 的 前方（如果 ego 面朝右下）")

print("\n=== 检查 ego 的朝向 ===")
# 根据 ego -> pedestrian5 = back-right (-139.6°)
# pedestrian5 在 (675.53, 1576.1)
# ego 在 (688.33, 1575.98)
# 全局方向：ped5 在 ego 的左边（x更小），y基本相同
# 如果 ego->ped5 是 back-right，说明 ego 面朝的方向使得"左边"变成"后右"
# 这意味着 ego 大约面朝 东北方向（图的右上）

print("推断：ego 大约面朝图的右上方（东北方向）")
print("因此：")
print("  - truck1 在 ego 的右前方")
print("  - ped7/8 在图的左上方")
print("  - 从 ego frame 看 truck1->ped7/8：应该往左上方，即 ego frame 的 front-left 或 left")
print("  - 但场景图显示是 'front' (angle=18.5°)")

print("\n=== 这说明什么？===")
print("场景图的 angle=18.5° 对应的 direction_8='front' 是正确的 ego frame 计算")
print("但从视觉上（BEV）看，ped7/8 确实在 truck1 的'后右'方向（从 truck 自身视角）")
print()
print("关键问题：'back-right of the truck' 是指：")
print("  1. ego frame 下 truck->ped 的方向？（场景图存储的）")
print("  2. truck 自身坐标系下的方向？（人类自然语言理解的）")
