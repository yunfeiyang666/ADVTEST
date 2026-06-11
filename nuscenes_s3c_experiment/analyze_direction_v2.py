"""
重新设计的方向分析脚本 v2
核心逻辑：对于每道方向题，计算source到所有可能target的方向，
看哪种计算方法能让至少一个对象落在期望方向上
"""

import json
import math
import re
import os
from nuscenes.nuscenes import NuScenes

# 配置
NUSCENES_DATAROOT = r"E:\Project\ADVTEST\data\nuscenes"
QA_FILE = r"E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json"
OUTPUT_FILE = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\direction_analysis_v2.txt"

# 测试的场景和帧
TEST_FRAMES = [
    ("scene-0103", 25),
    ("scene-0103", 38),
    ("scene-0553", 8),
    ("scene-0916", 8),
]

def quaternion_to_yaw(q):
    """四元数转yaw角(度)"""
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return math.degrees(yaw)

def normalize_angle(angle):
    """标准化角度到-180~180"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def angle_to_direction(angle):
    """角度转8方向"""
    angle = normalize_angle(angle)
    if -22.5 <= angle < 22.5:
        return 'front'
    elif 22.5 <= angle < 67.5:
        return 'front-left'
    elif 67.5 <= angle < 112.5:
        return 'left'
    elif 112.5 <= angle < 157.5:
        return 'back-left'
    elif angle >= 157.5 or angle < -157.5:
        return 'back'
    elif -157.5 <= angle < -112.5:
        return 'back-right'
    elif -112.5 <= angle < -67.5:
        return 'right'
    else:
        return 'front-right'

def calculate_all_directions(source_pos, source_heading, target_pos, ego_heading):
    """计算三种方向"""
    dx = target_pos[0] - source_pos[0]
    dy = target_pos[1] - source_pos[1]
    
    # Global (北=0)
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # Ego frame
    ego_heading_north = normalize_angle(90 - ego_heading)
    ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
    
    # Source frame
    source_heading_north = normalize_angle(90 - source_heading)
    source_frame_angle = normalize_angle(global_angle - source_heading_north)
    
    return {
        'global': (angle_to_direction(global_angle), global_angle),
        'ego_frame': (angle_to_direction(ego_frame_angle), ego_frame_angle),
        'source_frame': (angle_to_direction(source_frame_angle), source_frame_angle),
    }

def extract_direction_from_question(question):
    """从问题中提取方向词"""
    # 复合方向优先
    directions = ['front-left', 'front-right', 'back-left', 'back-right', 'front', 'back', 'left', 'right']
    q_lower = question.lower()
    
    # 替换空格版本为连字符版本
    q_lower = q_lower.replace('front left', 'front-left')
    q_lower = q_lower.replace('front right', 'front-right')
    q_lower = q_lower.replace('back left', 'back-left')
    q_lower = q_lower.replace('back right', 'back-right')
    
    found = []
    for d in directions:
        if d in q_lower:
            found.append(d)
    return found

def parse_direction_relations(question):
    """解析问题中的方向关系"""
    relations = []
    q_lower = question.lower()
    q_lower = q_lower.replace('front left', 'front-left')
    q_lower = q_lower.replace('front right', 'front-right')
    q_lower = q_lower.replace('back left', 'back-left')
    q_lower = q_lower.replace('back right', 'back-right')
    
    direction_patterns = ['front-left', 'front-right', 'back-left', 'back-right', 'front', 'back', 'left', 'right']
    
    for direction in direction_patterns:
        pattern = rf'to\s+the\s+{re.escape(direction)}\s+of\s+(?:the\s+)?([^,;?]+?)(?:\s+and|\s*;|\s*\?|,|$)'
        matches = re.findall(pattern, q_lower)
        
        for source_desc in matches:
            source_desc = source_desc.strip()
            if not source_desc:
                continue
            
            is_ego = source_desc in ['me', 'i']
            relations.append({
                'direction': direction,
                'source_desc': source_desc,
                'is_ego': is_ego
            })
    
    return relations

def get_object_by_type_status(ann, nusc):
    """从annotation获取对象类型和状态"""
    category = ann['category_name']
    
    obj_type = None
    if 'vehicle.car' in category:
        obj_type = 'car'
    elif 'vehicle.truck' in category:
        obj_type = 'truck'
    elif 'vehicle.bus' in category:
        obj_type = 'bus'
    elif 'human.pedestrian' in category:
        obj_type = 'pedestrian'
    elif 'vehicle.bicycle' in category:
        obj_type = 'bicycle'
    elif 'vehicle.motorcycle' in category:
        obj_type = 'motorcycle'
    elif 'vehicle.trailer' in category:
        obj_type = 'trailer'
    
    if obj_type is None:
        return None, None
    
    attrs = [nusc.get('attribute', a)['name'] for a in ann['attribute_tokens']]
    obj_status = 'unknown'
    for attr in attrs:
        if 'moving' in attr:
            obj_status = 'moving'
        elif 'stopped' in attr or 'parked' in attr:
            obj_status = 'stopped'
        elif 'standing' in attr or 'sitting' in attr:
            obj_status = 'standing'
        elif 'with_rider' in attr:
            obj_status = 'with_rider'
        elif 'without_rider' in attr:
            obj_status = 'without_rider'
    
    return obj_type, obj_status

def find_source_object(sample, source_desc, nusc, ego_pos):
    """根据描述找source对象"""
    desc_lower = source_desc.lower()
    
    # 提取类型和状态关键词
    type_keywords = {'car', 'truck', 'bus', 'pedestrian', 'bicycle', 'motorcycle', 'trailer'}
    status_keywords = {'moving', 'stopped', 'parked', 'standing', 'with_rider', 'without_rider', 
                       'with rider', 'without rider', 'not standing'}
    
    target_type = None
    target_status = None
    
    for t in type_keywords:
        if t in desc_lower:
            target_type = t
            break
    
    for s in status_keywords:
        if s in desc_lower:
            target_status = s.replace(' ', '_')
            if target_status == 'not_standing':
                target_status = 'moving'  # not standing = moving
            break
    
    # 找匹配的对象
    candidates = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        obj_type, obj_status = get_object_by_type_status(ann, nusc)
        
        if obj_type is None:
            continue
        
        # 类型匹配
        if target_type and obj_type != target_type:
            # 特殊处理: "thing" 匹配所有
            if 'thing' not in desc_lower:
                continue
        
        # 状态匹配
        if target_status:
            if target_status == 'parked' and obj_status != 'stopped':
                continue
            elif target_status not in ['parked'] and obj_status != target_status:
                continue
        
        pos = ann['translation']
        dist = math.sqrt((pos[0]-ego_pos[0])**2 + (pos[1]-ego_pos[1])**2)
        
        candidates.append({
            'type': obj_type,
            'status': obj_status,
            'pos': (pos[0], pos[1]),
            'heading': quaternion_to_yaw(ann['rotation']),
            'dist': dist
        })
    
    # 按距离排序，取最近的
    if candidates:
        candidates.sort(key=lambda x: x['dist'])
        return candidates[0]
    return None

def main():
    print("初始化NuScenes...")
    nusc = NuScenes(version='v1.0-trainval', dataroot=NUSCENES_DATAROOT, verbose=False)
    
    print("加载QA数据集...")
    with open(QA_FILE, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    # 建立sample_token到场景帧的映射
    sample_to_scene = {}
    for scene in nusc.scene:
        scene_name = scene['name']
        sample_token = scene['first_sample_token']
        frame_idx = 0
        while sample_token:
            sample_to_scene[sample_token] = (scene_name, frame_idx)
            sample = nusc.get('sample', sample_token)
            sample_token = sample['next']
            frame_idx += 1
    
    # 找出测试帧的sample_token
    test_tokens = set()
    for scene_name, frame_idx in TEST_FRAMES:
        for scene in nusc.scene:
            if scene['name'] == scene_name:
                sample_token = scene['first_sample_token']
                for i in range(frame_idx):
                    sample = nusc.get('sample', sample_token)
                    sample_token = sample['next']
                test_tokens.add(sample_token)
                break
    
    # 筛选相关问题
    direction_questions = []
    for q in qa_data['questions']:
        if q['sample_token'] in test_tokens:
            directions = extract_direction_from_question(q['question'])
            if directions:
                direction_questions.append(q)
    
    print(f"找到 {len(direction_questions)} 道涉及方向的题目")
    
    # 分析结果
    results = []
    
    # 统计
    stats = {
        'total': 0,
        'global_match': 0,
        'ego_frame_match': 0, 
        'source_frame_match': 0,
        'ego_questions': {'total': 0, 'global': 0, 'ego_frame': 0, 'source_frame': 0},
        'obj_questions': {'total': 0, 'global': 0, 'ego_frame': 0, 'source_frame': 0},
    }
    
    for q in direction_questions:
        sample_token = q['sample_token']
        scene_name, frame_idx = sample_to_scene[sample_token]
        sample = nusc.get('sample', sample_token)
        
        # 获取ego位置和朝向
        ego_pose_token = sample['data']['LIDAR_TOP']
        sample_data = nusc.get('sample_data', ego_pose_token)
        ego_pose = nusc.get('ego_pose', sample_data['ego_pose_token'])
        ego_pos = (ego_pose['translation'][0], ego_pose['translation'][1])
        ego_heading = quaternion_to_yaw(ego_pose['rotation'])
        
        # 解析方向关系
        relations = parse_direction_relations(q['question'])
        
        result = {
            'scene': scene_name,
            'frame': frame_idx,
            'question': q['question'],
            'answer': q['answer'],
            'relations': []
        }
        
        for rel in relations:
            expected_dir = rel['direction']
            
            rel_result = {
                'expected_direction': expected_dir,
                'source_desc': rel['source_desc'],
                'is_ego': rel['is_ego'],
                'global_matches': [],
                'ego_frame_matches': [],
                'source_frame_matches': [],
            }
            
            # 获取source
            if rel['is_ego']:
                source_pos = ego_pos
                source_heading = ego_heading
                rel_result['source_info'] = f"ego pos=({ego_pos[0]:.1f},{ego_pos[1]:.1f}) heading={ego_heading:.1f}°"
            else:
                source = find_source_object(sample, rel['source_desc'], nusc, ego_pos)
                if source is None:
                    rel_result['error'] = f"Cannot find source: {rel['source_desc']}"
                    result['relations'].append(rel_result)
                    continue
                source_pos = source['pos']
                source_heading = source['heading']
                rel_result['source_info'] = f"{source['type']}({source['status']}) pos=({source_pos[0]:.1f},{source_pos[1]:.1f}) heading={source_heading:.1f}°"
            
            # 遍历所有对象，看哪些在期望方向上（根据不同方法）
            obj_count = 0
            for ann_token in sample['anns']:
                ann = nusc.get('sample_annotation', ann_token)
                obj_type, obj_status = get_object_by_type_status(ann, nusc)
                if obj_type is None:
                    continue
                
                target_pos = (ann['translation'][0], ann['translation'][1])
                
                # 跳过自己
                if abs(target_pos[0]-source_pos[0]) < 0.1 and abs(target_pos[1]-source_pos[1]) < 0.1:
                    continue
                
                obj_count += 1
                dirs = calculate_all_directions(source_pos, source_heading, target_pos, ego_heading)
                
                obj_label = f"{obj_type}{obj_count}({obj_status}) pos=({target_pos[0]:.1f},{target_pos[1]:.1f})"
                
                if dirs['global'][0] == expected_dir:
                    rel_result['global_matches'].append({
                        'obj': obj_label,
                        'angle': dirs['global'][1]
                    })
                if dirs['ego_frame'][0] == expected_dir:
                    rel_result['ego_frame_matches'].append({
                        'obj': obj_label,
                        'angle': dirs['ego_frame'][1]
                    })
                if dirs['source_frame'][0] == expected_dir:
                    rel_result['source_frame_matches'].append({
                        'obj': obj_label,
                        'angle': dirs['source_frame'][1]
                    })
            
            # 统计
            stats['total'] += 1
            if rel_result['global_matches']:
                stats['global_match'] += 1
            if rel_result['ego_frame_matches']:
                stats['ego_frame_match'] += 1
            if rel_result['source_frame_matches']:
                stats['source_frame_match'] += 1
            
            if rel['is_ego']:
                stats['ego_questions']['total'] += 1
                if rel_result['global_matches']:
                    stats['ego_questions']['global'] += 1
                if rel_result['ego_frame_matches']:
                    stats['ego_questions']['ego_frame'] += 1
                if rel_result['source_frame_matches']:
                    stats['ego_questions']['source_frame'] += 1
            else:
                stats['obj_questions']['total'] += 1
                if rel_result['global_matches']:
                    stats['obj_questions']['global'] += 1
                if rel_result['ego_frame_matches']:
                    stats['obj_questions']['ego_frame'] += 1
                if rel_result['source_frame_matches']:
                    stats['obj_questions']['source_frame'] += 1
            
            result['relations'].append(rel_result)
        
        results.append(result)
    
    # 输出到文件
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("NuScenes-QA 方向计算方法对比分析 V2\n")
        f.write("=" * 80 + "\n\n")
        f.write("分析方法: 对于每个方向关系，检查是否存在对象在期望方向上\n")
        f.write("三种度量方式:\n")
        f.write("1. global    - 全局坐标系 (北=0°)\n")
        f.write("2. ego_frame - 以ego车朝向为0度参考\n")
        f.write("3. source_frame - 以source对象朝向为0度参考\n")
        f.write("\n" + "=" * 80 + "\n\n")
        
        for i, r in enumerate(results, 1):
            f.write(f"问题 {i}: [{r['scene']} frame {r['frame']}]\n")
            f.write(f"Q: {r['question']}\n")
            f.write(f"A: {r['answer']}\n")
            f.write("-" * 60 + "\n")
            
            for rel in r['relations']:
                f.write(f"  期望方向: {rel['expected_direction']}\n")
                f.write(f"  Source: {rel.get('source_info', rel['source_desc'])}\n")
                
                if 'error' in rel:
                    f.write(f"  错误: {rel['error']}\n")
                else:
                    f.write(f"  Global匹配 ({len(rel['global_matches'])}个):\n")
                    for m in rel['global_matches'][:3]:
                        f.write(f"    - {m['obj']} angle={m['angle']:.1f}°\n")
                    
                    f.write(f"  Ego_frame匹配 ({len(rel['ego_frame_matches'])}个):\n")
                    for m in rel['ego_frame_matches'][:3]:
                        f.write(f"    - {m['obj']} angle={m['angle']:.1f}°\n")
                    
                    f.write(f"  Source_frame匹配 ({len(rel['source_frame_matches'])}个):\n")
                    for m in rel['source_frame_matches'][:3]:
                        f.write(f"    - {m['obj']} angle={m['angle']:.1f}°\n")
                    
                    # 判断哪个方法有匹配
                    methods = []
                    if rel['global_matches']:
                        methods.append('global')
                    if rel['ego_frame_matches']:
                        methods.append('ego_frame')
                    if rel['source_frame_matches']:
                        methods.append('source_frame')
                    
                    if methods:
                        f.write(f"  >>> 有对象匹配的方法: {methods}\n")
                    else:
                        f.write(f"  >>> 所有方法都无匹配!\n")
                
                f.write("\n")
            
            f.write("=" * 80 + "\n\n")
        
        # 统计汇总
        f.write("=" * 80 + "\n")
        f.write("统计汇总\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"总计 {stats['total']} 个方向关系:\n")
        if stats['total'] > 0:
            f.write(f"  global 有匹配:       {stats['global_match']} ({100*stats['global_match']/stats['total']:.1f}%)\n")
            f.write(f"  ego_frame 有匹配:    {stats['ego_frame_match']} ({100*stats['ego_frame_match']/stats['total']:.1f}%)\n")
            f.write(f"  source_frame 有匹配: {stats['source_frame_match']} ({100*stats['source_frame_match']/stats['total']:.1f}%)\n")
        
        f.write(f"\nEgo相关问题 ({stats['ego_questions']['total']}个):\n")
        if stats['ego_questions']['total'] > 0:
            t = stats['ego_questions']['total']
            f.write(f"  global:       {stats['ego_questions']['global']} ({100*stats['ego_questions']['global']/t:.1f}%)\n")
            f.write(f"  ego_frame:    {stats['ego_questions']['ego_frame']} ({100*stats['ego_questions']['ego_frame']/t:.1f}%)\n")
            f.write(f"  source_frame: {stats['ego_questions']['source_frame']} ({100*stats['ego_questions']['source_frame']/t:.1f}%)\n")
        
        f.write(f"\nObject-to-Object问题 ({stats['obj_questions']['total']}个):\n")
        if stats['obj_questions']['total'] > 0:
            t = stats['obj_questions']['total']
            f.write(f"  global:       {stats['obj_questions']['global']} ({100*stats['obj_questions']['global']/t:.1f}%)\n")
            f.write(f"  ego_frame:    {stats['obj_questions']['ego_frame']} ({100*stats['obj_questions']['ego_frame']/t:.1f}%)\n")
            f.write(f"  source_frame: {stats['obj_questions']['source_frame']} ({100*stats['obj_questions']['source_frame']/t:.1f}%)\n")
    
    print(f"分析完成! 结果保存到: {OUTPUT_FILE}")
    
    # 打印统计
    print(f"\n统计 (共 {stats['total']} 个方向关系):")
    if stats['total'] > 0:
        print(f"  global 有匹配:       {stats['global_match']} ({100*stats['global_match']/stats['total']:.1f}%)")
        print(f"  ego_frame 有匹配:    {stats['ego_frame_match']} ({100*stats['ego_frame_match']/stats['total']:.1f}%)")
        print(f"  source_frame 有匹配: {stats['source_frame_match']} ({100*stats['source_frame_match']/stats['total']:.1f}%)")
    
    print(f"\n=== Ego相关问题 ({stats['ego_questions']['total']}个) ===")
    if stats['ego_questions']['total'] > 0:
        t = stats['ego_questions']['total']
        print(f"  global:       {stats['ego_questions']['global']} ({100*stats['ego_questions']['global']/t:.1f}%)")
        print(f"  ego_frame:    {stats['ego_questions']['ego_frame']} ({100*stats['ego_questions']['ego_frame']/t:.1f}%)")
        print(f"  source_frame: {stats['ego_questions']['source_frame']} ({100*stats['ego_questions']['source_frame']/t:.1f}%)")
    
    print(f"\n=== Object-to-Object问题 ({stats['obj_questions']['total']}个) ===")
    if stats['obj_questions']['total'] > 0:
        t = stats['obj_questions']['total']
        print(f"  global:       {stats['obj_questions']['global']} ({100*stats['obj_questions']['global']/t:.1f}%)")
        print(f"  ego_frame:    {stats['obj_questions']['ego_frame']} ({100*stats['obj_questions']['ego_frame']/t:.1f}%)")
        print(f"  source_frame: {stats['obj_questions']['source_frame']} ({100*stats['obj_questions']['source_frame']/t:.1f}%)")

if __name__ == '__main__':
    main()
