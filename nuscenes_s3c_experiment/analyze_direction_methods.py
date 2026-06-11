"""
分析58道QA题目的方向计算方法对比
对比三种度量方式:
1. ego frame - 所有方向以ego车朝向为参考
2. source frame - 方向以描述源对象的朝向为参考  
3. global/map - 方向直接用全局坐标系计算，不考虑任何朝向

输出: 每道涉及方向的题目的四种方位记录
"""

import json
import math
import re
import os
from nuscenes.nuscenes import NuScenes

# 配置
NUSCENES_DATAROOT = r"E:\Project\ADVTEST\data\nuscenes"
QA_FILE = r"E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json"
OUTPUT_FILE = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\direction_analysis.txt"

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

def calculate_direction_methods(source_pos, source_heading, target_pos, ego_heading):
    """
    计算三种方向度量方式
    source_pos: 源对象位置 (x, y)
    source_heading: 源对象朝向 (度)
    target_pos: 目标对象位置 (x, y)
    ego_heading: ego车朝向 (度)
    
    返回: (global_dir, ego_frame_dir, source_frame_dir, global_angle, ego_angle, source_angle)
    """
    dx = target_pos[0] - source_pos[0]
    dy = target_pos[1] - source_pos[1]
    
    # 修正: 全局角度使用 atan2(dx, dy) 让 0度=北(Y+), 90度=东(X+)
    # atan2(dx, dy) -> 北=0, 东=90, 西=-90, 南=180/-180
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # ego frame: 相对于ego朝向
    # ego_heading 也需要转换为北基准: heading_north = 90 - heading_east
    ego_heading_north = normalize_angle(90 - ego_heading)
    ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
    
    # source frame: 相对于source对象朝向
    source_heading_north = normalize_angle(90 - source_heading)
    source_frame_angle = normalize_angle(global_angle - source_heading_north)
    
    return (
        angle_to_direction(global_angle),
        angle_to_direction(ego_frame_angle),
        angle_to_direction(source_frame_angle),
        global_angle,
        ego_frame_angle,
        source_frame_angle
    )

def extract_direction_from_question(question):
    """从问题中提取方向词"""
    directions = ['front-left', 'front-right', 'back-left', 'back-right', 'front', 'back', 'left', 'right']
    found = []
    q_lower = question.lower()
    for d in directions:
        if d in q_lower:
            found.append(d)
    return found

def parse_question_structure(question):
    """
    解析问题结构，提取涉及的方向关系
    返回: [(source_desc, direction, target_desc), ...]
    """
    relations = []
    q_lower = question.lower()
    
    # NuScenes-QA使用空格分隔的方向词，如 "back right" 而不是 "back-right"
    # 复合方向必须放在前面，否则会被单一方向先匹配
    direction_patterns = [
        ('front left', 'front-left'),
        ('front right', 'front-right'),
        ('back left', 'back-left'),
        ('back right', 'back-right'),
        ('front', 'front'),
        ('back', 'back'),
        ('left', 'left'),
        ('right', 'right'),
    ]
    
    for dir_text, dir_normalized in direction_patterns:
        # 匹配 "to the DIRECTION of SOMETHING" 或 "to the DIRECTION of me"
        pattern = rf'to\s+the\s+{re.escape(dir_text)}\s+of\s+(?:the\s+)?([\w\s]+?)(?:\s+and|\s*;|\s*\?|,|$)'
        matches = re.findall(pattern, q_lower)
        
        for source_desc in matches:
            source_desc = source_desc.strip()
            # 过滤空匹配
            if not source_desc:
                continue
            
            # 检查是否是ego相关
            if source_desc in ['me', 'i']:
                relations.append({
                    'target': 'object',
                    'direction': dir_normalized,
                    'source': 'ego'
                })
            else:
                relations.append({
                    'target': 'object',
                    'direction': dir_normalized,
                    'source': source_desc
                })
    
    return relations

def get_object_by_description(annotations, desc, nusc, sample, source_pos=None):
    """根据描述找到对象，如果传入source_pos则按距离排序"""
    desc_lower = desc.lower().strip()
    
    # 处理特殊描述
    status_keywords = ['moving', 'stopped', 'parked', 'standing', 'with rider', 'without rider']
    type_keywords = ['car', 'truck', 'bus', 'pedestrian', 'bicycle', 'motorcycle', 'trailer', 'thing']
    
    target_status = None
    target_type = None
    
    for s in status_keywords:
        if s in desc_lower:
            target_status = s.replace(' ', '_')
            break
    
    for t in type_keywords:
        if t in desc_lower:
            target_type = t
            break
    
    # 查找匹配的对象
    candidates = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        category = ann['category_name']
        
        # 映射类型
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
            continue
            
        # 类型匹配
        if target_type and target_type != 'thing' and obj_type != target_type:
            continue
        
        # 获取状态
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
        
        # 状态匹配
        if target_status:
            if target_status == 'parked' and obj_status not in ['stopped', 'parked']:
                continue
            elif target_status not in ['parked'] and obj_status != target_status:
                continue
        
        candidates.append({
            'token': ann_token,
            'type': obj_type,
            'status': obj_status,
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'instance_token': ann['instance_token']  # 用于生成unique_id
        })
    
    # 如果传入了参考点source_pos，按距离排序（近邻原则）
    if source_pos and candidates:
        candidates.sort(key=lambda x: (x['translation'][0]-source_pos[0])**2 + (x['translation'][1]-source_pos[1])**2)
    
    return candidates

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
    
    print(f"测试帧tokens: {test_tokens}")
    
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
        
        # 解析问题中的方向关系
        relations = parse_question_structure(q['question'])
        
        result = {
            'scene': scene_name,
            'frame': frame_idx,
            'question': q['question'],
            'answer': q['answer'],
            'directions_in_question': extract_direction_from_question(q['question']),
            'analysis': []
        }
        
        for rel in relations:
            analysis_item = {
                'relation': f"{rel['target']} to {rel['direction']} of {rel['source']}",
                'expected_direction': rel['direction'],
                'calculated': {}
            }
            
            # 获取source和target对象
            if rel['source'] == 'ego':
                source_pos = ego_pos
                source_heading = ego_heading
                source_label = f"ego pos=({ego_pos[0]:.1f},{ego_pos[1]:.1f}) heading={ego_heading:.1f}°"
            else:
                source_candidates = get_object_by_description(sample['anns'], rel['source'], nusc, sample, ego_pos)
                if source_candidates:
                    src = source_candidates[0]
                    source_pos = (src['translation'][0], src['translation'][1])
                    source_heading = quaternion_to_yaw(src['rotation'])
                    source_label = f"{src['type']}1({src['status']}) pos=({source_pos[0]:.1f},{source_pos[1]:.1f}) heading={source_heading:.1f}°"
                else:
                    analysis_item['calculated']['error'] = f"Cannot find source: {rel['source']}"
                    result['analysis'].append(analysis_item)
                    continue
            
            analysis_item['source_info'] = source_label
            
            # 获取target对象，按距离source排序
            target_candidates = get_object_by_description(sample['anns'], rel['target'], nusc, sample, source_pos)
            if not target_candidates:
                # 尝试从答案推断目标类型
                target_candidates = get_object_by_description(sample['anns'], q['answer'], nusc, sample, source_pos)
            
            if target_candidates:
                for idx, tgt in enumerate(target_candidates[:3]):  # 只取前3个候选
                    target_pos = (tgt['translation'][0], tgt['translation'][1])
                    # 生成unique_id: type + 序号
                    target_id = f"{tgt['type']}{idx+1}"
                    target_label = f"{target_id}({tgt['status']}) pos=({tgt['translation'][0]:.1f},{tgt['translation'][1]:.1f})"
                    
                    global_dir, ego_dir, src_dir, g_ang, e_ang, s_ang = calculate_direction_methods(
                        source_pos, source_heading, target_pos, ego_heading
                    )
                    
                    analysis_item['calculated'][target_label] = {
                        'global': f"{global_dir} ({g_ang:.1f}°)",
                        'ego_frame': f"{ego_dir} ({e_ang:.1f}°)",
                        'source_frame': f"{src_dir} ({s_ang:.1f}°)",
                    }
            else:
                analysis_item['calculated']['error'] = f"Cannot find target for: {rel['target']}"
            
            result['analysis'].append(analysis_item)
        
        results.append(result)
    
    # 输出到文件
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("NuScenes-QA 方向计算方法对比分析\n")
        f.write("=" * 80 + "\n\n")
        f.write("三种度量方式:\n")
        f.write("1. global    - 全局坐标系角度 (atan2直接计算)\n")
        f.write("2. ego_frame - 以ego车朝向为0度参考\n")
        f.write("3. source_frame - 以描述源对象朝向为0度参考\n")
        f.write("\n" + "=" * 80 + "\n\n")
        
        for i, r in enumerate(results, 1):
            f.write(f"问题 {i}: [{r['scene']} frame {r['frame']}]\n")
            f.write(f"Q: {r['question']}\n")
            f.write(f"A: {r['answer']}\n")
            f.write(f"问题中的方向词: {r['directions_in_question']}\n")
            f.write("-" * 60 + "\n")
            
            for a in r['analysis']:
                f.write(f"  关系: {a['relation']}\n")
                f.write(f"  期望方向: {a['expected_direction']}\n")
                if 'source_info' in a:
                    f.write(f"  Source: {a['source_info']}\n")
                
                if 'error' in a['calculated']:
                    f.write(f"  错误: {a['calculated']['error']}\n")
                else:
                    for obj, dirs in a['calculated'].items():
                        if obj != 'error':
                            f.write(f"  目标 {obj}:\n")
                            f.write(f"    global:       {dirs['global']}\n")
                            f.write(f"    ego_frame:    {dirs['ego_frame']}\n")
                            f.write(f"    source_frame: {dirs['source_frame']}\n")
                            
                            # 标记哪个匹配
                            matches = []
                            if a['expected_direction'] in dirs['global']:
                                matches.append('global')
                            if a['expected_direction'] in dirs['ego_frame']:
                                matches.append('ego_frame')
                            if a['expected_direction'] in dirs['source_frame']:
                                matches.append('source_frame')
                            
                            if matches:
                                f.write(f"    >>> 匹配: {', '.join(matches)}\n")
                            else:
                                f.write(f"    >>> 无匹配!\n")
            
            f.write("\n" + "=" * 80 + "\n\n")
    
    print(f"分析完成! 结果保存到: {OUTPUT_FILE}")
    
    # 统计
    total_relations = 0
    match_global = 0
    match_ego = 0
    match_source = 0
    
    for r in results:
        for a in r['analysis']:
            if 'error' not in a['calculated']:
                for obj, dirs in a['calculated'].items():
                    if obj != 'error':
                        total_relations += 1
                        if a['expected_direction'] in dirs['global']:
                            match_global += 1
                        if a['expected_direction'] in dirs['ego_frame']:
                            match_ego += 1
                        if a['expected_direction'] in dirs['source_frame']:
                            match_source += 1
    
    print(f"\n统计 (共 {total_relations} 个方向关系):")
    print(f"  global 匹配:       {match_global} ({100*match_global/total_relations:.1f}%)" if total_relations > 0 else "  无数据")
    print(f"  ego_frame 匹配:    {match_ego} ({100*match_ego/total_relations:.1f}%)" if total_relations > 0 else "")
    print(f"  source_frame 匹配: {match_source} ({100*match_source/total_relations:.1f}%)" if total_relations > 0 else "")
    
    # 分类统计: ego相关 vs object-to-object
    ego_total = ego_g = ego_e = ego_s = 0
    obj_total = obj_g = obj_e = obj_s = 0
    
    for r in results:
        for a in r['analysis']:
            if 'error' not in a['calculated']:
                is_ego = 'ego' in a['relation'].lower()
                for obj, dirs in a['calculated'].items():
                    if obj != 'error':
                        if is_ego:
                            ego_total += 1
                            if a['expected_direction'] in dirs['global']:
                                ego_g += 1
                            if a['expected_direction'] in dirs['ego_frame']:
                                ego_e += 1
                            if a['expected_direction'] in dirs['source_frame']:
                                ego_s += 1
                        else:
                            obj_total += 1
                            if a['expected_direction'] in dirs['global']:
                                obj_g += 1
                            if a['expected_direction'] in dirs['ego_frame']:
                                obj_e += 1
                            if a['expected_direction'] in dirs['source_frame']:
                                obj_s += 1
    
    print(f"\n=== Ego相关问题 ({ego_total}个) ===")
    if ego_total > 0:
        print(f"  global:       {ego_g} ({100*ego_g/ego_total:.1f}%)")
        print(f"  ego_frame:    {ego_e} ({100*ego_e/ego_total:.1f}%)")
        print(f"  source_frame: {ego_s} ({100*ego_s/ego_total:.1f}%)")
    
    print(f"\n=== Object-to-Object问题 ({obj_total}个) ===")
    if obj_total > 0:
        print(f"  global:       {obj_g} ({100*obj_g/obj_total:.1f}%)")
        print(f"  ego_frame:    {obj_e} ({100*obj_e/obj_total:.1f}%)")
        print(f"  source_frame: {obj_s} ({100*obj_s/obj_total:.1f}%)")
    
    # 追加统计到文件末尾
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("统计汇总\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"总计 {total_relations} 个方向关系:\n")
        if total_relations > 0:
            f.write(f"  global 匹配:       {match_global} ({100*match_global/total_relations:.1f}%)\n")
            f.write(f"  ego_frame 匹配:    {match_ego} ({100*match_ego/total_relations:.1f}%)\n")
            f.write(f"  source_frame 匹配: {match_source} ({100*match_source/total_relations:.1f}%)\n")
        
        f.write(f"\nEgo相关问题 ({ego_total}个):\n")
        if ego_total > 0:
            f.write(f"  global:       {ego_g} ({100*ego_g/ego_total:.1f}%)\n")
            f.write(f"  ego_frame:    {ego_e} ({100*ego_e/ego_total:.1f}%)\n")
            f.write(f"  source_frame: {ego_s} ({100*ego_s/ego_total:.1f}%)\n")
        
        f.write(f"\nObject-to-Object问题 ({obj_total}个):\n")
        if obj_total > 0:
            f.write(f"  global:       {obj_g} ({100*obj_g/obj_total:.1f}%)\n")
            f.write(f"  ego_frame:    {obj_e} ({100*obj_e/obj_total:.1f}%)\n")
            f.write(f"  source_frame: {obj_s} ({100*obj_s/obj_total:.1f}%)\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("结论\n")
        f.write("=" * 80 + "\n")
        f.write("\n根据统计结果:\n")
        f.write("1. Ego相关问题: global方法匹配率最高\n")
        f.write("   -> NuScenes-QA对ego问题使用全局坐标系\n")
        f.write("2. Object-to-Object问题: ego_frame方法匹配率最高\n")
        f.write("   -> NuScenes-QA对object-to-object问题使用相对于ego朝向的参考系\n")
        f.write("\n建议策略:\n")
        f.write("- 对于含'me'的ego相关问题: 使用global坐标系计算方向\n")
        f.write("- 对于object-to-object问题: 使用ego_frame坐标系计算方向\n")

if __name__ == '__main__':
    main()
