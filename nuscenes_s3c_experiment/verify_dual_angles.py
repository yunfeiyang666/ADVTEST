import json

# 加载新生成的场景图
with open('output/scene_graphs/all_scene_graphs_full_relation.json', 'r', encoding='utf-8') as f:
    scene_graphs = json.load(f)

# 找到scene-0103
for sg in scene_graphs:
    if sg['scene_name'] == 'scene-0103':
        print(f"Scene: {sg['scene_name']}")
        print(f"Number of objects: {len(sg['objects'])}")
        print(f"Objects: {[o['unique_id'] for o in sg['objects']]}")
        
        # 查找car到pedestrian的关系（取前3个）
        print("\n" + "="*60)
        print("Car -> Pedestrian relationships (first 3):")
        print("="*60)
        count = 0
        for rel in sg['relationships']:
            if 'car' in rel['source'] and 'pedestrian' in rel['target']:
                print(f"\n{rel['source']} -> {rel['target']}:")
                print(f"  predicates: {rel['predicates']}")
                print(f"  distance: {rel['metrics']['distance']}")
                print(f"  Source Frame:")
                print(f"    angle: {rel['metrics']['angle_source']}")
                print(f"    direction_8: {rel['metrics']['direction_source']['direction_8']}")
                print(f"    angle_matches: {rel['metrics']['direction_source']['angle_matches']}")
                print(f"  Ego Frame:")
                print(f"    angle: {rel['metrics']['angle_ego']}")
                print(f"    direction_8: {rel['metrics']['direction_ego']['direction_8']}")
                print(f"    angle_matches: {rel['metrics']['direction_ego']['angle_matches']}")
                count += 1
                if count >= 3:
                    break
        break
else:
    print('scene-0103 not found')
    print('Available scenes:', [sg['scene_name'] for sg in scene_graphs])
