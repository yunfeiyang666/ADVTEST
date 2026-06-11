"""
NuScenes场景覆盖分析
找出有代表性的帧（对象多/少），分析VQA问题覆盖情况
"""
import os
import sys
from collections import defaultdict

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
import config


def analyze_all_scenes():
    """分析所有场景的对象分布"""
    print("=" * 60)
    print("  NuScenes 场景覆盖分析")
    print("=" * 60)
    
    # 加载NuScenes
    print("\n加载NuScenes数据集...")
    nusc = NuScenes(
        version='v1.0-mini',
        dataroot=config.NUSCENES_DATAROOT,
        verbose=False
    )
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 分析每个场景的每一帧
    scene_stats = []
    
    for scene in nusc.scene:
        scene_name = scene['name']
        sample_token = scene['first_sample_token']
        
        frame_idx = 0
        while sample_token:
            sample = nusc.get('sample', sample_token)
            
            # 统计对象
            annotations = sample['anns']
            obj_count = len(annotations)
            
            # 按类型统计
            type_counts = defaultdict(int)
            for ann_token in annotations:
                ann = nusc.get('sample_annotation', ann_token)
                category = ann['category_name'].split('.')[0]  # 取第一级类别
                type_counts[category] += 1
            
            scene_stats.append({
                'scene_name': scene_name,
                'sample_token': sample_token,
                'frame_idx': frame_idx,
                'total_objects': obj_count,
                'type_counts': dict(type_counts),
                'description': scene['description']
            })
            
            sample_token = sample['next']
            frame_idx += 1
    
    print(f"✓ 分析了 {len(scene_stats)} 帧")
    
    return scene_stats


def find_representative_frames(scene_stats):
    """找出有代表性的帧"""
    print("\n" + "=" * 60)
    print("  代表性帧分析")
    print("=" * 60)
    
    # 按对象数量排序
    sorted_by_count = sorted(scene_stats, key=lambda x: x['total_objects'], reverse=True)
    
    # 对象最多的帧
    print("\n📈 对象最多的5帧:")
    print("-" * 60)
    for i, frame in enumerate(sorted_by_count[:5], 1):
        types_str = ", ".join([f"{k}:{v}" for k, v in frame['type_counts'].items()])
        print(f"  {i}. {frame['scene_name']} 帧{frame['frame_idx']}: {frame['total_objects']}个对象")
        print(f"     类型: {types_str}")
    
    # 对象最少的帧
    print("\n📉 对象最少的5帧:")
    print("-" * 60)
    for i, frame in enumerate(sorted_by_count[-5:], 1):
        types_str = ", ".join([f"{k}:{v}" for k, v in frame['type_counts'].items()])
        print(f"  {i}. {frame['scene_name']} 帧{frame['frame_idx']}: {frame['total_objects']}个对象")
        print(f"     类型: {types_str}")
    
    # 统计分布
    counts = [f['total_objects'] for f in scene_stats]
    print("\n📊 对象数量分布:")
    print("-" * 60)
    print(f"  最小: {min(counts)} 个")
    print(f"  最大: {max(counts)} 个")
    print(f"  平均: {sum(counts)/len(counts):.1f} 个")
    
    # 分段统计
    ranges = [(0, 10), (10, 20), (20, 30), (30, 50), (50, 100), (100, 200)]
    print("\n  对象数量区间分布:")
    for low, high in ranges:
        count = sum(1 for c in counts if low <= c < high)
        if count > 0:
            print(f"    {low}-{high}: {count} 帧 ({count/len(counts)*100:.1f}%)")
    
    return {
        'max_objects': sorted_by_count[:5],
        'min_objects': sorted_by_count[-5:],
        'stats': {
            'min': min(counts),
            'max': max(counts),
            'avg': sum(counts)/len(counts),
            'total_frames': len(counts)
        }
    }


def analyze_question_coverage(representative_frames):
    """分析VQA问题对代表性帧的覆盖情况"""
    print("\n" + "=" * 60)
    print("  VQA问题覆盖分析")
    print("=" * 60)
    
    from vqa_pipeline.sample_questions import NUSCENES_QA_QUESTIONS, DRIVELM_QUESTIONS
    
    # 问题类型统计
    question_types = {
        'count': '计数问题 - 适合对象多的场景',
        'existence': '存在性问题 - 适合任何场景',
        'status': '状态问题 - 适合有特定对象的场景',
        'spatial': '空间关系问题 - 适合对象多且分布复杂的场景',
        'comparison': '比较问题 - 适合有多个同类对象的场景',
        'complex': '复合问题 - 需要丰富的场景',
    }
    
    print("\n问题类型与场景适配分析:")
    print("-" * 60)
    
    for qtype, desc in question_types.items():
        q_count = len(NUSCENES_QA_QUESTIONS.get(qtype, []))
        print(f"\n  {qtype} ({q_count}个问题):")
        print(f"    {desc}")
        
        # 分析适合的帧
        if qtype in ['count', 'spatial', 'complex']:
            # 适合对象多的场景
            suitable = representative_frames['max_objects']
            print(f"    推荐场景: 对象多的帧（如 {suitable[0]['scene_name']} 帧{suitable[0]['frame_idx']}）")
        elif qtype == 'existence':
            # 适合任何场景
            print(f"    推荐场景: 任意帧都适合")
        elif qtype in ['status', 'comparison']:
            # 适合中等复杂度
            print(f"    推荐场景: 对象数量适中的帧")
    
    # 覆盖率分析
    print("\n" + "-" * 60)
    print("\n覆盖率评估:")
    
    # 基于我们的问题集
    total_questions = sum(len(qs) for qs in NUSCENES_QA_QUESTIONS.values())
    total_questions += sum(len(qs) for qs in DRIVELM_QUESTIONS.values())
    
    coverage_analysis = {
        'count_questions': len(NUSCENES_QA_QUESTIONS.get('count', [])),
        'spatial_questions': len(NUSCENES_QA_QUESTIONS.get('spatial', [])),
        'existence_questions': len(NUSCENES_QA_QUESTIONS.get('existence', [])),
        'total_questions': total_questions,
    }
    
    print(f"  总问题数: {total_questions}")
    print(f"  计数类: {coverage_analysis['count_questions']} 个")
    print(f"  空间类: {coverage_analysis['spatial_questions']} 个")
    print(f"  存在类: {coverage_analysis['existence_questions']} 个")
    
    # 场景覆盖建议
    print("\n场景选择建议:")
    print("-" * 60)
    print("  1. 对象密集场景: 测试计数、空间关系问题")
    print("  2. 对象稀疏场景: 测试存在性、边界情况问题")
    print("  3. 多类型混合场景: 测试比较、分类问题")
    print("  4. 复杂交通场景: 测试DriveLM风格的规划问题")
    
    return coverage_analysis


def main():
    """主函数"""
    # 分析所有场景
    scene_stats = analyze_all_scenes()
    
    # 找代表性帧
    representative = find_representative_frames(scene_stats)
    
    # 分析问题覆盖
    coverage = analyze_question_coverage(representative)
    
    print("\n" + "=" * 60)
    print("  分析完成")
    print("=" * 60)
    
    print("\n推荐用于测试的帧:")
    print("-" * 60)
    
    # 对象最多
    max_frame = representative['max_objects'][0]
    print(f"\n  🔵 高密度场景: {max_frame['scene_name']} 帧{max_frame['frame_idx']}")
    print(f"     对象数: {max_frame['total_objects']}")
    print(f"     描述: {max_frame['description']}")
    
    # 对象最少
    min_frame = representative['min_objects'][-1]
    print(f"\n  🔴 低密度场景: {min_frame['scene_name']} 帧{min_frame['frame_idx']}")
    print(f"     对象数: {min_frame['total_objects']}")
    print(f"     描述: {min_frame['description']}")


if __name__ == "__main__":
    main()
