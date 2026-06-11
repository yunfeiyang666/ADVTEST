"""分析Q4题目的方向问题"""
import json

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', encoding='utf-8'))

# 找motorcycle和truck
moto = None
truck = None
ego = None
for n in sg['nodes']:
    if n['type'] == 'motorcycle':
        moto = n
    if n['type'] == 'truck':
        truck = n
    if n['unique_id'] == 'ego':
        ego = n

print('=== 对象信息 ===')
print(f"Motorcycle: {moto['unique_id']}, status={moto['status']}")
print(f"Truck: {truck['unique_id']}, status={truck['status']}")
print()

# 找moto->truck的关系
print('=== motorcycle -> truck 关系 ===')
for r in sg['edges']:
    if r['source'] == moto['unique_id'] and r['target'] == truck['unique_id']:
        print(f"方向: {r['predicates'][0]}, 距离: {r['predicates'][1]}")
        print(f"角度: {r['metrics']['angle']}")
        break
else:
    print("未找到关系!")

# 找ego->truck的关系
print()
print('=== ego -> truck 关系 ===')
for r in sg['edges']:
    if r['source'] == 'ego' and r['target'] == truck['unique_id']:
        print(f"方向: {r['predicates'][0]}, 距离: {r['predicates'][1]}")
        print(f"角度: {r['metrics']['angle']}")
        break
else:
    print("未找到关系!")

print()
print('=== 期望的方向 ===')
print('题目要求: motorcycle的back-right, ego的front-left')
print()
print('=== 结论 ===')
print('如果实际方向与期望方向不匹配，说明:')
print('1. 要么QA数据集的标注有问题')
print('2. 要么我们的方向计算方法与QA生成脚本不一致')
