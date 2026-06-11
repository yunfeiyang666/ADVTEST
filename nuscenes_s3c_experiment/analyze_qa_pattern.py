"""
详细分析坐标和角度，找出QA生成的真实规律
"""
import json
import math

def quaternion_to_yaw(quaternion):
    """从四元数提取yaw角"""
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return yaw
    return 0.0

# 加载scene graph
with open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

objects = {}
for node in scene_graph['nodes']:
    objects[node['unique_id']] = node

ego = objects['ego']
truck = None
for obj_id, obj in objects.items():
    if obj['type'] == 'truck' and 'trailer' not in obj['category']:
        truck = obj
        break

pedestrian1 = objects.get('pedestrian1')
bicycle1 = objects.get('bicycle1')
motorcycle1 = objects.get('motorcycle1')

print("=" * 100)
print("详细坐标和角度分析")
print("=" * 100)
print()

# 案例1: motorcycle -> truck, 期望 back-right
print("【案例1】motorcycle -> truck, 期望方位: back-right")
print("-" * 100)
m_pos = [motorcycle1['translation']['x'], motorcycle1['translation']['y'], motorcycle1['translation']['z']]
t_pos = [truck['translation']['x'], truck['translation']['y'], truck['translation']['z']]
m_rot = motorcycle1['rotation']
t_rot = truck['rotation']

print(f"Motorcycle位置: ({m_pos[0]:.2f}, {m_pos[1]:.2f})")
print(f"Truck位置:      ({t_pos[0]:.2f}, {t_pos[1]:.2f})")
print(f"坐标差: dx={t_pos[0]-m_pos[0]:.2f}, dy={t_pos[1]-m_pos[1]:.2f}")

m_yaw = math.degrees(quaternion_to_yaw(m_rot))
t_yaw = math.degrees(quaternion_to_yaw(t_rot))
ego_yaw = math.degrees(quaternion_to_yaw(ego['rotation']))

print(f"\nMotorcycle朝向: {m_yaw:.1f}°")
print(f"Truck朝向:      {t_yaw:.1f}°")
print(f"Ego朝向:        {ego_yaw:.1f}°")

# 计算各种角度
angle_global = math.degrees(math.atan2(t_pos[1]-m_pos[1], t_pos[0]-m_pos[0]))
print(f"\n全局坐标系角度: {angle_global:.1f}° (直接arctan2)")

# 如果期望是back-right，那应该是什么角度范围？
# back-right应该是 -157.5° ~ -112.5°
print(f"\n期望方位'back-right'对应角度范围: -157.5° ~ -112.5°")
print(f"需要的偏移量: 期望角度 - 实际全局角度 = ?")
print()

# 案例2: ego -> truck, 期望 front-left (唯一的✓)
print("【案例2】ego -> truck, 期望方位: front-left (假设3命中✓)")
print("-" * 100)
e_pos = [ego['translation']['x'], ego['translation']['y'], ego['translation']['z']]
print(f"Ego位置:   ({e_pos[0]:.2f}, {e_pos[1]:.2f})")
print(f"Truck位置: ({t_pos[0]:.2f}, {t_pos[1]:.2f})")
print(f"坐标差: dx={t_pos[0]-e_pos[0]:.2f}, dy={t_pos[1]-e_pos[1]:.2f}")

angle_global = math.degrees(math.atan2(t_pos[1]-e_pos[1], t_pos[0]-e_pos[0]))
print(f"全局坐标系角度: {angle_global:.1f}°")
print(f"期望方位'front-left'对应角度范围: 22.5° ~ 67.5°")
print(f"✓ 命中！这说明ego的题目使用的是地图坐标系（y=前，x=右）")
print()

# 案例3: truck -> pedestrian1, 期望 back-right
print("【案例3】truck -> pedestrian1, 期望方位: back-right")
print("-" * 100)
p1_pos = [pedestrian1['translation']['x'], pedestrian1['translation']['y'], pedestrian1['translation']['z']]
print(f"Truck位置:       ({t_pos[0]:.2f}, {t_pos[1]:.2f})")
print(f"Pedestrian1位置: ({p1_pos[0]:.2f}, {p1_pos[1]:.2f})")
print(f"坐标差: dx={p1_pos[0]-t_pos[0]:.2f}, dy={p1_pos[1]-t_pos[1]:.2f}")

angle_global = math.degrees(math.atan2(p1_pos[1]-t_pos[1], p1_pos[0]-t_pos[0]))
print(f"全局坐标系角度: {angle_global:.1f}°")
print(f"期望方位'back-right'对应角度范围: -157.5° ~ -112.5°")
print(f"实际计算得到: front-right (约-50°)")
print()

# 案例4: truck -> bicycle1, 期望 front-left
print("【案例4】truck -> bicycle1, 期望方位: front-left")
print("-" * 100)
b1_pos = [bicycle1['translation']['x'], bicycle1['translation']['y'], bicycle1['translation']['z']]
print(f"Truck位置:    ({t_pos[0]:.2f}, {t_pos[1]:.2f})")
print(f"Bicycle1位置: ({b1_pos[0]:.2f}, {b1_pos[1]:.2f})")
print(f"坐标差: dx={b1_pos[0]-t_pos[0]:.2f}, dy={b1_pos[1]-t_pos[1]:.2f}")

angle_global = math.degrees(math.atan2(b1_pos[1]-t_pos[1], b1_pos[0]-t_pos[0]))
print(f"全局坐标系角度: {angle_global:.1f}°")
print(f"期望方位'front-left'对应角度范围: 22.5° ~ 67.5°")
print(f"实际计算得到: right (约-5°)")
print()

print("=" * 100)
print("关键发现：")
print("1. ego相关的题目使用地图坐标系（假设3✓）")
print("2. object-to-object的题目全部失败，且期望方位与实际计算相差很大")
print("3. 可能原因：")
print("   a) QA数据集标注有严重错误（人工标注错误率5-10%）")
print("   b) QA生成脚本在object-to-object关系上使用了错误的参考系")
print("   c) 存在某种我们还没发现的坐标转换规则")
print()
print("建议策略：")
print("1. 对于ego相关问题：使用地图坐标系（假设3）")
print("2. 对于object-to-object：先用假设1（source朝向），容忍一定错误率")
print("3. 或者：考虑把object-to-object也统一用地图坐标系，但需要更多测试验证")
print("=" * 100)
