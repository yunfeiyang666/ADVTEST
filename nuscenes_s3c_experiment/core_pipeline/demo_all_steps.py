"""
全流程演示脚本 — 逐步展示每个组件的实际输出
用于汇报展示

运行方式:
  python -m core_pipeline.demo_all_steps
  (从 nuscenes_s3c_experiment 目录运行)
"""
import sys, json, os

# 确保 nuscenes_s3c_experiment 在 path 中
_core = os.path.dirname(os.path.abspath(__file__))
_experiment = os.path.dirname(_core)
if _experiment not in sys.path:
    sys.path.insert(0, _experiment)
if _core not in sys.path:
    sys.path.insert(0, _core)

# ============================================================
#  STEP 1: 模板库统计
# ============================================================
def step1_template_library():
    print("=" * 70)
    print("  STEP 1: 模板库 (Template Library) 统计")
    print("=" * 70)
    from qa_generator_v2.template_library import get_template_library, TemplateEntry
    lib = get_template_library()
    
    # 获取所有模板
    all_t = lib.get_all()
    
    print(f"\n总模板数: {len(all_t)}")
    
    # 按覆盖层级
    from collections import Counter, defaultdict
    level_count = Counter(t.coverage_level for t in all_t)
    type_count = Counter(t.question_type for t in all_t)
    lt_count = Counter((t.coverage_level, t.question_type) for t in all_t)
    
    print("\n--- 按覆盖层级 ---")
    for k in sorted(level_count):
        print(f"  {k}: {level_count[k]} 个模板")
    
    print("\n--- 按问题类型 ---")
    for k in sorted(type_count):
        print(f"  {k}: {type_count[k]} 个模板")
    
    print("\n--- 层级 × 类型 交叉表 ---")
    for k in sorted(lt_count):
        print(f"  {k[0]}-{k[1]}: {lt_count[k]}")
    
    # 每个层级展示2个样例
    print("\n--- 每层级样例模板 ---")
    shown = defaultdict(int)
    for t in all_t:
        if shown[t.coverage_level] < 2:
            print(f"\n  [{t.template_id}]")
            print(f"    模板: {t.template}")
            print(f"    答案类型: {t.answer_type}, 答案逻辑: {t.answer_logic}")
            print(f"    所需参数: {t.required_params}")
            shown[t.coverage_level] += 1
    
    return len(all_t)


# ============================================================
#  STEP 2: 覆盖率数据流
# ============================================================
def step2_coverage_data_flow():
    print("\n" + "=" * 70)
    print("  STEP 2: 覆盖率数据流 (Coverage Data Flow)")
    print("=" * 70)
    
    sg_dir = os.path.join(os.path.dirname(__file__), 
                          "output", "coverage_analysis", "scene_graphs")
    
    # 列出所有场景图文件
    sg_files = [f for f in os.listdir(sg_dir) 
                if f.endswith("_scene_graph.json")]
    print(f"\n场景图文件目录: {sg_dir}")
    print(f"已有场景图: {len(sg_files)} 个")
    for f in sg_files:
        fpath = os.path.join(sg_dir, f)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  {f} ({size_kb:.0f} KB)")
    
    # 选一个场景图展示结构
    sample_file = os.path.join(sg_dir, sg_files[0])
    with open(sample_file, encoding="utf-8") as fp:
        sg = json.load(fp)
    
    nodes = sg.get("nodes", [])
    edges = sg.get("edges", [])
    print(f"\n--- 场景图样例: {sg_files[0]} ---")
    print(f"  场景: {sg.get('scene_name')}, 帧: {sg.get('frame_idx')}")
    print(f"  节点数: {len(nodes)}")
    print(f"  边数: {len(edges)}")
    
    # 节点类型分布
    from collections import Counter
    type_dist = Counter(n.get("type") for n in nodes)
    print(f"  节点类型分布: {dict(type_dist)}")
    
    status_dist = Counter(n.get("status") for n in nodes)
    print(f"  状态分布: {dict(status_dist)}")
    
    # 展示一个节点和一条边
    non_ego = [n for n in nodes if n.get("type") != "ego"]
    if non_ego:
        sample_node = non_ego[0]
        print(f"\n  样例节点: {json.dumps(sample_node, indent=4, ensure_ascii=False)[:500]}")
    if edges:
        sample_edge = edges[0]
        print(f"\n  样例边: {json.dumps(sample_edge, indent=4, ensure_ascii=False)[:500]}")
    
    # 初始化 CoverageTracker
    from qa_generator_v2.coverage_tracker import CoverageTracker
    tracker = CoverageTracker.from_scene_graph(sg)
    rates = tracker.coverage_rates()
    
    print(f"\n--- CoverageTracker 初始化结果 ---")
    print(f"  L0 (节点覆盖): {rates['L0_detail']['total']} 个, 覆盖率 {rates['L0']:.1%}")
    print(f"  L1 (边覆盖):   {rates['L1_detail']['total']} 条, 覆盖率 {rates['L1']:.1%}")
    print(f"  L2 (两跳路径): {rates['L2_detail']['total']} 条, 覆盖率 {rates['L2']:.1%}")
    
    return sg, tracker


# ============================================================
#  STEP 3: 覆盖率驱动生成 (一轮)
# ============================================================
def step3_generation(sg, tracker):
    print("\n" + "=" * 70)
    print("  STEP 3: 覆盖率驱动生成 (一轮演示)")
    print("=" * 70)
    
    from qa_generator_v2.template_filler import TemplateFiller
    from qa_generator_v2.coverage_driven_template_generator import CoverageDrivenTemplateGenerator, CoverageGoal
    
    generator = CoverageDrivenTemplateGenerator(sg)
    
    # 聚焦 L0，生成 5 题作为演示
    goal = CoverageGoal(focus_level="L0", target=1.0, max_questions=5)
    
    print(f"\n生成目标: 聚焦 {goal.focus_level}, 预算 {goal.max_questions} 题")
    
    # 查看初始缺口
    rates_before = tracker.coverage_rates()
    print(f"\n--- 生成前覆盖率 ---")
    print(f"  L0: {rates_before['L0_detail']['covered']}/{rates_before['L0_detail']['total']} = {rates_before['L0']:.1%}")
    
    gen_result = generator.generate_with_tracker(tracker, goal)
    qa_list = gen_result.questions
    
    rates_after = tracker.coverage_rates()
    print(f"\n--- 生成后覆盖率 ---")
    print(f"  L0: {rates_after['L0_detail']['covered']}/{rates_after['L0_detail']['total']} = {rates_after['L0']:.1%}")
    print(f"  L0 覆盖率提升: {rates_before['L0']:.1%} → {rates_after['L0']:.1%}")
    print(f"  缺口填补: {gen_result.gaps_filled}/{gen_result.gaps_total}")
    print(f"  生成耗时: {gen_result.generation_time:.2f}s")
    
    print(f"\n--- 生成的 QA 样例 (共 {len(qa_list)} 题) ---")
    for i, qa in enumerate(qa_list[:5]):
        print(f"\n  Q{i+1}: {qa.get('question', '')}")
        print(f"  A{i+1}: {qa.get('answer', '')}")
        print(f"  模板: {qa.get('template_id', '')}, 类型: {qa.get('question_type', '')}")
        print(f"  覆盖元素: {qa.get('covered_elements', [])}")
    
    # 再做一轮 L1
    print(f"\n--- 第二轮: 聚焦 L1 ---")
    goal_l1 = CoverageGoal(focus_level="L1", target=0.1, max_questions=5)
    gen_result_l1 = generator.generate_with_tracker(tracker, goal_l1)
    qa_list_l1 = gen_result_l1.questions
    rates_l1 = tracker.coverage_rates()
    print(f"  L1: {rates_after['L1_detail']['covered']}/{rates_after['L1_detail']['total']} → {rates_l1['L1_detail']['covered']}/{rates_l1['L1_detail']['total']}")
    
    for i, qa in enumerate(qa_list_l1[:3]):
        print(f"\n  Q{i+1}: {qa.get('question', '')}")
        print(f"  A{i+1}: {qa.get('answer', '')}")
        print(f"  模板: {qa.get('template_id', '')}")
    
    all_qa = qa_list + qa_list_l1
    return all_qa, tracker


# ============================================================
#  STEP 4: Phase 0 过滤展示
# ============================================================
def step4_filtering():
    print("\n" + "=" * 70)
    print("  STEP 4: Phase 0 过滤展示")
    print("=" * 70)
    
    from coverage_evaluation.scene_filter import SceneGraphFilter, QAFilter
    
    sg_dir = os.path.join(os.path.dirname(__file__), 
                          "output", "coverage_analysis", "scene_graphs")
    sg_files = [f for f in os.listdir(sg_dir) if f.endswith("_scene_graph.json")]
    sample_file = os.path.join(sg_dir, sg_files[0])
    
    with open(sample_file, encoding="utf-8") as fp:
        sg = json.load(fp)
    
    nodes_before = len(sg.get("nodes", []))
    edges_before = len(sg.get("edges", []))
    
    # 应用过滤
    filt = SceneGraphFilter(mode="filtered")
    filtered_sg = filt.filter_scene_graph(sg)
    
    nodes_after = len(filtered_sg.get("nodes", []))
    edges_after = len(filtered_sg.get("edges", []))
    
    print(f"\n--- 物体过滤 (SceneGraphFilter) ---")
    print(f"  过滤前: {nodes_before} 节点, {edges_before} 边")
    print(f"  过滤后: {nodes_after} 节点, {edges_after} 边")
    print(f"  移除: {nodes_before - nodes_after} 节点, {edges_before - edges_after} 边")
    
    # QA 过滤
    qa_filter = QAFilter()
    print(f"\n--- 错题过滤 (QAFilter) ---")
    print(f"  黑名单中共 {qa_filter.skip_count} 条错题记录")
    
    # 展示黑名单内容
    skip_path = os.path.join(os.path.dirname(__file__), 
                             "coverage_evaluation", "skip_questions.json")
    if os.path.exists(skip_path):
        with open(skip_path, encoding="utf-8") as fp:
            skip_data = json.load(fp)
        print(f"  黑名单文件: skip_questions.json")
        for item in skip_data.get("skip_list", [])[:3]:
            print(f"    [{item[0]}, frame {item[1]}, Q{item[2]}] {item[3]}")


# ============================================================
#  主入口
# ============================================================
if __name__ == "__main__":
    print("\n" + "#" * 70)
    print("#  覆盖率驱动 VLM 测试框架 — 全流程演示")
    print("#" * 70)
    
    # Step 1
    n_templates = step1_template_library()
    
    # Step 2
    sg, tracker = step2_coverage_data_flow()
    
    # Step 3
    all_qa, tracker = step3_generation(sg, tracker)
    
    # Step 4
    step4_filtering()
    
    # 最终总结
    rates = tracker.coverage_rates()
    print("\n" + "=" * 70)
    print("  最终覆盖率总结")
    print("=" * 70)
    print(f"  模板库: {n_templates} 个模板")
    print(f"  生成 QA: {len(all_qa)} 题")
    print(f"  L0 覆盖: {rates['L0']:.1%}")
    print(f"  L1 覆盖: {rates['L1']:.1%}")
    print(f"  L2 覆盖: {rates['L2']:.1%}")
    print("\n演示完成!")
