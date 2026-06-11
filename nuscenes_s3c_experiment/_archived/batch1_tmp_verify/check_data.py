import json

def get_nodes(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data.get('nodes', [])

# 检查各场景truck/trailer状态
for scene_file, scene_name in [
    ('output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json', 'scene-0103_frame25'),
    ('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'scene-0103_frame38'),
    ('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'scene-0553_frame8'),
    ('output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json', 'scene-0916_frame8'),
]:
    nodes = get_nodes(scene_file)
    print(f'\n=== {scene_name} ===')
    
    # trucks and trailers
    for obj in nodes:
        t = obj.get('type', '')
        cat = obj.get('category', '')
        if t == 'truck' or 'trailer' in cat.lower():
            print(f"  {obj.get('unique_id')}: type={t}, status={obj.get('status')}, cat={cat}")

# Q8分析：scene-0103_frame25中not standing pedestrian的back-right的car
print('\n=== Q8 Analysis: scene-0103_frame25 ===')
nodes = get_nodes('output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json')

# 找出not standing的pedestrians
not_standing_peds = [obj for obj in nodes if obj.get('type') == 'pedestrian' and obj.get('status') != 'standing']
print(f"Not standing pedestrians: {[(p.get('unique_id'), p.get('status')) for p in not_standing_peds]}")

# 找出所有cars
cars = [obj for obj in nodes if obj.get('type') == 'car']
print(f"\nAll cars ({len(cars)} total):")
for car in sorted(cars, key=lambda x: x.get('unique_id', ''))[:10]:  # 只显示前10个
    print(f"  {car.get('unique_id')}: status={car.get('status')}")
print(f"  ... (showing first 10 of {len(cars)})")

# 统计car状态分布
from collections import Counter
car_statuses = Counter(c.get('status') for c in cars)
print(f"\nCar status distribution: {dict(car_statuses)}")
