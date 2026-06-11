"""
分析NuScenes原始标注内容
理解"原始标注集"包含哪些信息
"""
import os
import sys
import json

devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
import config


def analyze_sample_annotations(nusc, sample_token):
    """分析单个sample的原始标注"""
    sample = nusc.get('sample', sample_token)
    
    print("\n" + "=" * 70)
    print("  NuScenes原始标注内容分析")
    print("=" * 70)
    
    # 1. 获取所有标注对象
    print(f"\n【原始标注对象数】: {len(sample['anns'])}")
    
    annotations = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        annotations.append(ann)
        
        if len(annotations) == 1:
            print("\n【标注对象示例】:")
            print(f"  Token: {ann['token']}")
            print(f"  类别: {ann['category_name']}")
            print(f"  位置: {ann['translation']}")
            print(f"  朝向: {ann['rotation']}")
            print(f"  尺寸: {ann['size']}")
            print(f"  可见性: {ann['visibility_token']}")
            print(f"  属性: {ann.get('attribute_tokens', [])}")
            print(f"  激光点数: {ann['num_lidar_pts']}")
            print(f"  雷达点数: {ann['num_radar_pts']}")
    
    # 2. 原始标注包含的字段
    if annotations:
        print("\n【原始标注字段清单】:")
        for key in sorted(annotations[0].keys()):
            print(f"  - {key}")
    
    # 3. 原始标注中的关系信息
    print("\n【原始标注中的关系信息】:")
    print("  ❌ NuScenes不包含对象间关系标注（如car1在car2前方）")
    print("  ❌ NuScenes不包含对象间距离标注")
    print("  ✅ 只有对象相对于ego车的位置（通过坐标计算）")
    
    # 4. 分析对象类别分布
    category_count = {}
    for ann in annotations:
        cat = ann['category_name']
        category_count[cat] = category_count.get(cat, 0) + 1
    
    print("\n【对象类别分布】:")
    for cat, count in sorted(category_count.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    # 5. 分析可见性
    visibility_count = {}
    for ann in annotations:
        vis_token = ann['visibility_token']
        vis_record = nusc.get('visibility', vis_token)
        vis_level = vis_record['level']
        visibility_count[vis_level] = visibility_count.get(vis_level, 0) + 1
    
    print("\n【可见性分布】:")
    for level, count in sorted(visibility_count.items()):
        print(f"  {level}: {count}")
    
    return annotations


def main():
    print("加载NuScenes数据集...")
    nusc = NuScenes(
        version='v1.0-mini',
        dataroot=config.NUSCENES_DATAROOT,
        verbose=False
    )
    
    # 选择一个有代表性的场景
    scene = nusc.scene[0]
    sample_token = scene['first_sample_token']
    
    print(f"\n分析场景: {scene['name']}")
    print(f"描述: {scene['description']}")
    
    annotations = analyze_sample_annotations(nusc, sample_token)
    
    # 总结
    print("\n" + "=" * 70)
    print("  关键结论")
    print("=" * 70)
    print("\n【NuScenes原始标注包含】:")
    print("  ✅ 对象类别（category_name）")
    print("  ✅ 3D边界框（translation, rotation, size）")
    print("  ✅ 可见性级别（visibility）")
    print("  ✅ 激光/雷达点数（num_lidar_pts, num_radar_pts）")
    print("  ✅ 速度（可通过box_velocity获取）")
    
    print("\n【NuScenes原始标注不包含】:")
    print("  ❌ 对象间空间关系（如'car1在car2前方'）")
    print("  ❌ 对象间距离")
    print("  ❌ 对象间相对角度")
    print("  ❌ VQA问答对")
    
    print("\n【我们的场景图生成】:")
    print("  🔧 基于原始标注对象计算全关系")
    print("  🔧 为每个对象分配unique_id")
    print("  🔧 计算所有对象对之间的空间关系")
    print("  🔧 添加方位谓词（front/left/right/rear）")
    print("  🔧 添加距离谓词（near/mid/far）")
    
    print("\n【覆盖率测试的正确理解】:")
    print("  1️⃣ 全集 = 场景图中所有对象 + 所有计算出的关系")
    print("  2️⃣ 原始标注 = NuScenes标注的对象（不含关系）")
    print("  3️⃣ VQA覆盖率 = VQA问题能否查询到标注对象及其关系")
    print("  4️⃣ 因此：覆盖率测试是针对'场景图全集'，而非'原始标注集'")


if __name__ == "__main__":
    main()
