"""
NuScenes VQA 示例问题集
基于市面上常见的NuScenes VQA问题类型
"""

# ============ NuScenes-QA 风格问题 ============
# 参考: https://github.com/qiantianwen/NuScenes-QA

NUSCENES_QA_QUESTIONS = {
    # 计数类问题
    "count": [
        "场景中有多少辆车？",
        "场景中有多少个行人？",
        "ego车前方有多少个对象？",
        "距离ego车10米内有多少个对象？",
        "场景中有多少辆卡车？",
        "ego左侧有多少个行人？",
        "场景中总共有多少种不同类型的交通参与者？",
    ],
    
    # 存在性问题 (是/否)
    "existence": [
        "ego车前方有车辆吗？",
        "场景中有行人吗？",
        "ego车左侧有卡车吗？",
        "car1前方有行人吗？",
        "距离ego车5米内有对象吗？",
        "场景中有公交车吗？",
        "ego后方有自行车吗？",
    ],
    
    # 对象状态问题
    "status": [
        "离ego最近的车辆是哪个？",
        "离ego最远的行人是哪个？",
        "哪个对象距离ego最近？",
        "car1距离ego多远？",
        "pedestrian1在ego的什么方向？",
        "truck1距离car1多远？",
    ],
    
    # 空间关系问题
    "spatial": [
        "ego车前方有哪些对象？",
        "car1的左侧有哪些车辆？",
        "pedestrian1在car1的什么方位？",
        "哪些对象在ego的后方？",
        "car1和car2之间的空间关系是什么？",
        "ego右侧最近的对象是什么？",
    ],
    
    # 比较类问题
    "comparison": [
        "car1和car2哪个离ego更近？",
        "场景中车辆多还是行人多？",
        "ego前方和后方哪边的对象更多？",
        "哪种类型的对象数量最多？",
    ],
    
    # 复合问题
    "complex": [
        "ego车前方最近的车辆是哪个？它距离ego多远？",
        "有多少个行人在ego的前方且距离小于20米？",
        "列出所有在ego车10米范围内的对象及其类型",
        "car1前方有哪些行人？分别距离多远？",
        "ego车周围最密集的方向是哪个？有多少对象？",
    ],
}

# ============ DriveLM 风格问题 ============
# 参考: https://github.com/OpenDriveLab/DriveLM

DRIVELM_QUESTIONS = {
    # 感知类问题
    "perception": [
        "描述ego车周围的交通参与者分布情况",
        "ego车前方有什么障碍物？",
        "场景中最需要注意的对象是什么？",
        "哪些对象可能对行驶安全构成威胁？",
    ],
    
    # 预测类问题
    "prediction": [
        "哪些对象可能进入ego的行驶路径？",
        "ego前方最近的行人可能的移动方向？",
        "需要特别关注哪个方向的交通参与者？",
    ],
    
    # 规划类问题
    "planning": [
        "ego车应该注意哪个方向的对象？",
        "当前场景中最安全的行驶方向是？",
        "是否需要减速？为什么？",
    ],
}

# ============ 汇总所有问题 ============
def get_all_questions():
    """获取所有示例问题"""
    all_questions = []
    
    for category, questions in NUSCENES_QA_QUESTIONS.items():
        for q in questions:
            all_questions.append({
                "question": q,
                "category": category,
                "source": "nuscenes-qa"
            })
    
    for category, questions in DRIVELM_QUESTIONS.items():
        for q in questions:
            all_questions.append({
                "question": q,
                "category": category,
                "source": "drivelm"
            })
    
    return all_questions


def get_questions_by_category(category: str):
    """按类别获取问题"""
    all_qs = NUSCENES_QA_QUESTIONS.get(category, [])
    all_qs.extend(DRIVELM_QUESTIONS.get(category, []))
    return all_qs


def print_question_stats():
    """打印问题统计"""
    print("=" * 60)
    print("  VQA问题集统计")
    print("=" * 60)
    
    print("\nNuScenes-QA风格问题:")
    total = 0
    for category, questions in NUSCENES_QA_QUESTIONS.items():
        print(f"  {category}: {len(questions)} 个")
        total += len(questions)
    print(f"  小计: {total} 个")
    
    print("\nDriveLM风格问题:")
    total2 = 0
    for category, questions in DRIVELM_QUESTIONS.items():
        print(f"  {category}: {len(questions)} 个")
        total2 += len(questions)
    print(f"  小计: {total2} 个")
    
    print(f"\n总计: {total + total2} 个问题")


if __name__ == "__main__":
    print_question_stats()
