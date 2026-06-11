#!/usr/bin/env python
"""
测试 nuImages 可见度筛选功能
"""
import os
import sys
import json
import logging

# 添加本地路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
import config
from core_pipeline.coverage_evaluation.scene_filter import SceneGraphFilter, filter_scene_graph_file

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_visibility_filtering():
    """测试可见度筛选功能"""
    
    print("=" * 80)
    print("测试 nuImages 可见度筛选")
    print("=" * 80)
    
    # 加载 nuScenes
    print("\n加载 nuScenes 数据集...")
    nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)
    
    # 测试场景图
    test_scene_graph = "E:\\Project\\ADVTEST\\nuscenes_s3c_experiment\\output\\coverage_analysis\\scene-0061_frame19_scene_graph.json"
    
    if not os.path.exists(test_scene_graph):
        print(f"场景图文件不存在: {test_scene_graph}")
        return
    
    # 加载场景图
    with open(test_scene_graph, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    scene_name = scene_graph.get('scene_name')
    frame_idx = scene_graph.get('frame_idx')
    
    print(f"\n测试场景: {scene_name}, Frame: {frame_idx}")
    print(f"原始节点数: {len(scene_graph.get('nodes', []))}")
    
    # 查找 sample_token
    try:
        scene_rec = nusc.get('scene', nusc.field2token('scene', 'name', scene_name)[0])
        sample = nusc.get('sample', scene_rec['first_sample_token'])
        for _ in range(frame_idx):
            if sample['next']:
                sample = nusc.get('sample', sample['next'])
        sample_token = sample['token']
        print(f"Sample token: {sample_token}")
    except Exception as e:
        print(f"无法查找 sample_token: {e}")
        return
    
    # 创建筛选器（带 nuScenes 支持）
    print("\n" + "=" * 80)
    print("筛选模式: 使用 nuScenes API 查询 visibility")
    print("=" * 80)
    
    filter_with_visibility = SceneGraphFilter(
        mode='filtered', 
        nusc=nusc, 
        sample_token=sample_token
    )
    
    filtered_graph = filter_with_visibility.filter_scene_graph(scene_graph)
    
    print(f"\n筛选结果:")
    print(f"  保留节点: {len(filtered_graph.get('nodes', []))}/{len(scene_graph.get('nodes', []))}")
    
    # 检查 visibility 缓存
    print(f"\nVisibility 查询结果:")
    print(f"  缓存大小: {len(filter_with_visibility._visibility_cache)} 个节点")
    
    if filter_with_visibility._visibility_cache:
        print("\n查询到的 visibility 值：")
        for node_id, vis in list(filter_with_visibility._visibility_cache.items())[:5]:
            print(f"    {node_id}: {vis:.2f}")
        if len(filter_with_visibility._visibility_cache) > 5:
            print(f"    ... 及其他 {len(filter_with_visibility._visibility_cache) - 5} 个")
    else:
        print("  ⚠️  没有匹配到任何 visibility 数据")
    
    # 统计可见度信息
    print("\n" + "=" * 80)
    print("可见度统计")
    print("=" * 80)
    
    sample = nusc.get('sample', sample_token)
    visibility_stats = {}
    
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        if ann.get('visibility_token'):
            vis_token = ann['visibility_token']
            vis_record = nusc.get('visibility', vis_token)
            vis_level = vis_record['level']
            visibility_stats[vis_level] = visibility_stats.get(vis_level, 0) + 1
    
    print("\n可见度分布:")
    for level in sorted(visibility_stats.keys()):
        count = visibility_stats[level]
        print(f"  {level}: {count} 个对象")
    
    # 对比筛选前后
    print("\n" + "=" * 80)
    print("筛选标准对比")
    print("=" * 80)
    
    print("\nnuScenes 标准:")
    print(f"  - 距离阈值: {filter_with_visibility.DETECTION_RANGES}")
    print(f"  - 可见度阈值: {filter_with_visibility.MIN_VISIBILITY_NUSCENES * 100:.0f}% (nuScenes)")
    print(f"  - 可见度阈值: {filter_with_visibility.MIN_VISIBILITY_NUIMAGES * 100:.0f}% (nuImages)")
    print(f"  - 当前使用: {filter_with_visibility.MIN_VISIBILITY * 100:.0f}%")
    
    print("\nnuImages 标准:")
    print(f"  - 像素阈值: ≥ {filter_with_visibility.MIN_PIXELS_STRICT} pixels (宽度)")
    
    print("\n完成!")


if __name__ == '__main__':
    test_visibility_filtering()
