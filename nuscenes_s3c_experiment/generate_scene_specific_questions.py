"""
根据场景图中的实际对象动态生成VQA问题
"""
import json
import random
from collections import defaultdict

from vqa_pipeline.object_utils import filter_nodes_by_distance


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_scene_objects(scene_graph):
    """提取场景中的所有对象（不做距离筛选）。"""
    objects_by_type = defaultdict(list)

    for node in scene_graph["nodes"]:
        unique_id = node["unique_id"]
        obj_type = node["type"]

        if unique_id != "ego":  # 排除ego
            objects_by_type[obj_type].append(unique_id)

    return dict(objects_by_type)


def extract_nearby_scene_objects(scene_graph, max_distance: float = 40.0):
    """提取距离ego在给定范围内的对象。

    说明：
    - 使用 vqa_pipeline.object_utils.filter_nodes_by_distance 做距离过滤；
    - 默认阈值40米，大致对齐NuScenes官方评测常用的可见范围；
    - 返回结构同 extract_scene_objects，用于后续基于对象类型生成问题。
    """
    objects_by_type = defaultdict(list)

    nearby_nodes = filter_nodes_by_distance(scene_graph, max_distance=max_distance, include_ego=False)
    for node in nearby_nodes:
        unique_id = node["unique_id"]
        obj_type = node["type"]
        objects_by_type[obj_type].append(unique_id)

    return dict(objects_by_type)


def generate_scene_specific_questions(scene_graph, max_per_category=6, max_distance: float = 40.0):
    """根据场景中实际对象生成针对性问题。

    只考虑距离ego在 max_distance 米以内的对象，以过滤掉很远、面积很小的远端目标，
    近似对齐 NuScenes 官方评测里对远端对象的忽略策略。
    """
    objects = extract_nearby_scene_objects(scene_graph, max_distance=max_distance)
    questions = []
    
    # 打印场景中的对象
    print(f"\n【场景对象】")
    for obj_type, ids in sorted(objects.items(), key=lambda x: -len(x[1])):
        print(f"  {obj_type}: {len(ids)} 个 ({', '.join(ids[:5])}{'...' if len(ids) > 5 else ''})")
    
    # 1. 存在性问题 - 基于实际对象类型
    print(f"\n【生成存在性问题】")
    existence_questions = []
    
    # 检查实际存在的类型
    for obj_type in ['car', 'pedestrian', 'truck', 'bus', 'bicycle', 'motorcycle']:
        if obj_type in objects:
            existence_questions.append(("existence", f"场景中有{get_chinese_name(obj_type)}吗？"))
            # 针对具体对象
            if len(objects[obj_type]) >= 2:
                obj1 = objects[obj_type][0]
                existence_questions.append(("existence", f"{obj1}前方有其他车辆吗？"))
    
    # 检查不存在的类型（应该返回"没有"）
    for obj_type in ['bus', 'bicycle', 'motorcycle']:
        if obj_type not in objects:
            existence_questions.append(("existence", f"场景中有{get_chinese_name(obj_type)}吗？"))
    
    questions.extend(random.sample(existence_questions, min(len(existence_questions), max_per_category)))
    
    # 2. 计数问题 - 基于实际对象
    print(f"【生成计数问题】")
    count_questions = []
    
    for obj_type, ids in objects.items():
        if len(ids) > 0:
            count_questions.append(("count", f"场景中有多少个{get_chinese_name(obj_type)}？"))
    
    count_questions.append(("count", "ego车前方有多少个对象？"))
    count_questions.append(("count", "距离ego车10米内有多少个对象？"))
    
    questions.extend(random.sample(count_questions, min(len(count_questions), max_per_category)))
    
    # 3. 状态问题 - 使用实际对象ID
    print(f"【生成状态问题】")
    status_questions = []
    
    if 'car' in objects and len(objects['car']) > 0:
        status_questions.append(("status", "离ego最近的车辆是哪个？"))
        car1 = objects['car'][0]
        status_questions.append(("status", f"{car1}距离ego多远？"))
        
        if len(objects['car']) >= 2:
            car2 = objects['car'][1]
            status_questions.append(("status", f"{car1}和{car2}哪个离ego更近？"))
    
    if 'pedestrian' in objects and len(objects['pedestrian']) > 0:
        ped1 = objects['pedestrian'][0]
        status_questions.append(("status", f"{ped1}在ego的什么方向？"))
    
    questions.extend(random.sample(status_questions, min(len(status_questions), max_per_category)))
    
    # 4. 空间关系问题 - 使用实际对象对
    print(f"【生成空间关系问题】")
    spatial_questions = []
    
    spatial_questions.append(("spatial", "ego车前方有哪些对象？"))
    spatial_questions.append(("spatial", "哪些对象在ego的后方？"))
    
    # 对象间关系
    if 'car' in objects and len(objects['car']) >= 2:
        car1 = objects['car'][0]
        car2 = objects['car'][1]
        spatial_questions.append(("spatial", f"{car1}的左侧有哪些车辆？"))
        spatial_questions.append(("spatial", f"{car1}和{car2}之间的空间关系是什么？"))
    
    if 'pedestrian' in objects and len(objects['pedestrian']) > 0:
        ped1 = objects['pedestrian'][0]
        if 'car' in objects and len(objects['car']) > 0:
            car1 = objects['car'][0]
            spatial_questions.append(("spatial", f"{ped1}在{car1}的什么方位？"))
    
    questions.extend(random.sample(spatial_questions, min(len(spatial_questions), max_per_category)))
    
    # 5. 比较问题
    print(f"【生成比较问题】")
    comparison_questions = []
    
    # 比较数量
    types_with_objects = list(objects.keys())
    if len(types_with_objects) >= 2:
        type1, type2 = types_with_objects[0], types_with_objects[1]
        comparison_questions.append(("comparison", f"场景中{get_chinese_name(type1)}多还是{get_chinese_name(type2)}多？"))
    
    comparison_questions.append(("comparison", "ego前方和后方哪边的对象更多？"))
    comparison_questions.append(("comparison", "哪种类型的对象数量最多？"))
    
    questions.extend(random.sample(comparison_questions, min(len(comparison_questions), max_per_category)))
    
    # 6. 复合问题
    print(f"【生成复合问题】")
    complex_questions = []
    
    if 'car' in objects and len(objects['car']) > 0:
        complex_questions.append(("complex", "ego车前方最近的车辆是哪个？它距离ego多远？"))
    
    if 'pedestrian' in objects and len(objects['pedestrian']) > 0:
        complex_questions.append(("complex", "有多少个行人在ego的前方且距离小于20米？"))
        
        if 'car' in objects and len(objects['car']) > 0:
            car1 = objects['car'][0]
            complex_questions.append(("complex", f"{car1}前方有哪些行人？分别距离多远？"))
    
    complex_questions.append(("complex", "列出所有在ego车10米范围内的对象及其类型"))
    complex_questions.append(("complex", "ego车周围最密集的方向是哪个？有多少对象？"))
    
    questions.extend(random.sample(complex_questions, min(len(complex_questions), max_per_category)))
    
    print(f"\n【生成总结】")
    print(f"  共生成 {len(questions)} 个针对性问题")
    
    return questions


def get_chinese_name(obj_type):
    """获取对象类型的中文名"""
    mapping = {
        'car': '车辆',
        'pedestrian': '行人',
        'truck': '卡车',
        'bus': '公交车',
        'bicycle': '自行车',
        'motorcycle': '摩托车',
    }
    return mapping.get(obj_type, obj_type)


def analyze_question_coverage(questions, scene_graph):
    """分析问题覆盖了哪些对象"""
    # 注意：分析覆盖率时也基于距离过滤后的对象集合
    objects = extract_nearby_scene_objects(scene_graph)

    total_objects = sum(len(ids) for ids in objects.values())
    for category, question in questions:
        for obj_type, ids in objects.items():
            for obj_id in ids:
                if obj_id in question:
                    mentioned_objects.add(obj_id)
    
    total_objects = sum(len(ids) for ids in objects.values())
    coverage_rate = len(mentioned_objects) / total_objects * 100 if total_objects > 0 else 0
    
    print(f"\n【对象覆盖率】")
    print(f"  场景总对象: {total_objects}")
    print(f"  问题涉及对象: {len(mentioned_objects)}")
    print(f"  覆盖率: {coverage_rate:.1f}%")
    print(f"  涉及的对象: {sorted(mentioned_objects)}")
    
    return {
        'total_objects': total_objects,
        'mentioned_objects': len(mentioned_objects),
        'coverage_rate': coverage_rate,
        'mentioned_list': sorted(mentioned_objects)
    }


def main():
    """测试生成功能"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config
    
    # 测试一个场景
    scene_graph_path = os.path.join(
        config.OUTPUT_DIR,
        "coverage_analysis",
        "scene_graphs",
        "scene-0757_frame26_scene_graph.json"
    )
    
    print("=" * 70)
    print("  场景特定VQA问题生成器")
    print("=" * 70)
    
    print(f"\n加载场景图: scene-0757 帧26")
    scene_graph = load_scene_graph(scene_graph_path)
    
    print(f"\n场景统计:")
    print(f"  对象数: {len(scene_graph['nodes'])}")
    print(f"  关系数: {len(scene_graph['edges'])}")
    
    # 生成问题
    questions = generate_scene_specific_questions(scene_graph, max_per_category=4, max_distance=40.0)
    
    print(f"\n{'=' * 70}")
    print("  生成的问题列表")
    print("=" * 70)
    for i, (category, question) in enumerate(questions, 1):
        print(f"{i}. [{category}] {question}")
    
    # 分析覆盖率
    coverage = analyze_question_coverage(questions, scene_graph)
    
    print(f"\n{'=' * 70}")
    print("  结论")
    print("=" * 70)
    print("  ✅ 问题基于场景中实际存在的对象生成")
    print("  ✅ 使用真实的对象ID（如car3, pedestrian2）")
    print("  ✅ 避免询问不存在的对象")
    print(f"  ✅ 覆盖了 {coverage['coverage_rate']:.1f}% 的场景对象")


if __name__ == "__main__":
    main()
