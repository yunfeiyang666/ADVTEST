"""
多级路径覆盖率测试脚本（L=0,1,2）

设计目标：
- L0: 节点覆盖（至少通过一条被覆盖的边触达的节点）
- L1: 以 ego 为起点的一跳边覆盖（ego -> X）
- L2: 以 ego 为起点的两跳路径覆盖（ego -> A -> B）

依赖：
- 场景图 JSON（包含 nodes / edges）
- VQA 结果 JSON（包含 question / cypher_query）
- vqa_pipeline.scene_coverage.calculate_scene_coverage 用于计算边级覆盖

用法（示例）：
    python test_multi_level_coverage.py

如需更换场景，可修改 MAIN_SCENE_GRAPH / MAIN_VQA_RESULT 常量。
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set

from vqa_pipeline.scene_coverage import calculate_scene_coverage


# ====== 可按需修改：默认使用0553的官方QA和场景图 ======
MAIN_SCENE_GRAPH = Path("output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json")
MAIN_VQA_RESULT = Path("output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json")


def _load_scene_graph(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_questions_from_vqa(path: Path) -> List[Dict[str, Any]]:
    """从VQA结果JSON中提取 question + cypher_query 字段。

    兼容两种字段名：
    - 新流程通常使用 "cypher_query"
    - 旧 coverage 结果文件使用 "cypher"
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    questions = []
    for item in data.get("results", []):
        cypher = item.get("cypher_query") or item.get("cypher") or ""
        questions.append(
            {
                "question": item.get("question", ""),
                "cypher_query": cypher,
                "query_result": item.get("query_result", {}),
            }
        )
    return questions


def _build_edge_sets(edge_details: List[Dict[str, Any]]) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    """从 scene_coverage 的 edge_details 提取：
    - all_edges: 所有边 (source, target)
    - covered_edges: 被覆盖的边 (source, target)
    """
    all_edges: Set[Tuple[str, str]] = set()
    covered_edges: Set[Tuple[str, str]] = set()

    for e in edge_details:
        source = e.get("source")
        target = e.get("target")
        if not source or not target:
            continue
        edge = (source, target)
        all_edges.add(edge)
        if e.get("is_covered"):
            covered_edges.add(edge)

    return all_edges, covered_edges


def _compute_l0_node_coverage(scene_graph: Dict[str, Any], all_edges: Set[Tuple[str, str]], covered_edges: Set[Tuple[str, str]]) -> Dict[str, Any]:
    """L0: 节点覆盖

    定义：
    - total_nodes: 场景中节点总数（nodes 数量，如果没有 nodes 字段，则用边端点并集近似）
    - covered_nodes: 至少连接到一条被覆盖边的节点数
    """
    nodes = scene_graph.get("nodes") or []
    if nodes:
        all_node_ids = {n.get("id") or n.get("unique_id") for n in nodes}
        all_node_ids = {nid for nid in all_node_ids if nid}
    else:
        all_node_ids = set()
        for s, t in all_edges:
            all_node_ids.add(s)
            all_node_ids.add(t)

    # 通过被覆盖边触达的节点
    covered_node_ids: Set[str] = set()
    for s, t in covered_edges:
        covered_node_ids.add(s)
        covered_node_ids.add(t)

    total_nodes = len(all_node_ids)
    covered_nodes = len(covered_node_ids & all_node_ids) if all_node_ids else 0
    rate = (covered_nodes / total_nodes * 100) if total_nodes > 0 else 0.0

    return {
        "level": 0,
        "total": total_nodes,
        "covered": covered_nodes,
        "coverage_rate": round(rate, 2),
    }


def _compute_l1_edge_coverage_from_ego(all_edges: Set[Tuple[str, str]], covered_edges: Set[Tuple[str, str]]) -> Dict[str, Any]:
    """L1: 以 ego 为起点的一跳边覆盖

    total: 以 source == 'ego' 的边数量
    covered: 这些边中被覆盖的数量
    """
    ego_edges = {e for e in all_edges if e[0] == "ego"}
    covered_ego_edges = ego_edges & covered_edges

    total = len(ego_edges)
    covered = len(covered_ego_edges)
    rate = (covered / total * 100) if total > 0 else 0.0

    return {
        "level": 1,
        "total": total,
        "covered": covered,
        "coverage_rate": round(rate, 2),
    }


def _compute_l2_path_coverage_from_ego(all_edges: Set[Tuple[str, str]], covered_edges: Set[Tuple[str, str]]) -> Dict[str, Any]:
    """L2: 以 ego 为起点的两跳路径覆盖（ego -> A -> B）

    定义：
    - total: 所有满足 ego->A 和 A->B 存在的路径数量
    - covered: 这些路径中，两条边都在 covered_edges 集合中的路径数量

    注意：这里不区分是否在同一条查询中被使用，只要两条边都曾被覆盖即认为该路径被覆盖。
    这是一个近似但简单的上界估计，足以做整体统计用。
    """
    # 构建邻接表
    outgoing = {}
    for s, t in all_edges:
        outgoing.setdefault(s, set()).add(t)

    total_paths = 0
    covered_paths = 0

    # ego -> A -> B
    for mid in outgoing.get("ego", set()):
        # 边 (ego, mid)
        e1 = ("ego", mid)
        for dst in outgoing.get(mid, set()):
            e2 = (mid, dst)
            total_paths += 1
            if e1 in covered_edges and e2 in covered_edges:
                covered_paths += 1

    rate = (covered_paths / total_paths * 100) if total_paths > 0 else 0.0

    return {
        "level": 2,
        "total": total_paths,
        "covered": covered_paths,
        "coverage_rate": round(rate, 2),
    }


def compute_multi_level_coverage(scene_graph_path: Path, vqa_result_path: Path) -> Dict[str, Any]:
    """综合计算 L0/L1/L2 覆盖率，返回结构化结果。"""
    print("=" * 70)
    print("  多级路径覆盖率计算 (L=0,1,2)")
    print("=" * 70)

    print(f"\n加载场景图: {scene_graph_path}")
    scene_graph = _load_scene_graph(scene_graph_path)
    print(f"  节点数: {len(scene_graph.get('nodes', []))}")
    print(f"  边数: {len(scene_graph.get('edges', []))}")

    print(f"\n加载VQA结果: {vqa_result_path}")
    questions = _load_questions_from_vqa(vqa_result_path)
    print(f"  问题数: {len(questions)}")

    print("\n[Step 1] 计算边级覆盖 (基础)...")
    coverage_stats = calculate_scene_coverage(questions, scene_graph)
    edge_details = coverage_stats["edge_details"]
    all_edges, covered_edges = _build_edge_sets(edge_details)

    print("[Step 2] 计算多级路径覆盖...")
    l0 = _compute_l0_node_coverage(scene_graph, all_edges, covered_edges)
    l1 = _compute_l1_edge_coverage_from_ego(all_edges, covered_edges)
    l2 = _compute_l2_path_coverage_from_ego(all_edges, covered_edges)

    result = {
        "scene_graph": str(scene_graph_path),
        "vqa_results": str(vqa_result_path),
        "base_edge_coverage": {
            "total_edges": coverage_stats["total_edges"],
            "covered_edges": coverage_stats["covered_edges"],
            "coverage_rate": coverage_stats["coverage_rate"],
        },
        "multi_level": {
            "L0": l0,
            "L1": l1,
            "L2": l2,
        },
    }

    # 打印简要总结
    print("\n" + "=" * 70)
    print("  覆盖率总结")
    print("=" * 70)
    print(f"\n[Edge] 边级覆盖: {coverage_stats['covered_edges']} / {coverage_stats['total_edges']}  -> {coverage_stats['coverage_rate']}%")
    print(
        f"[L0] 节点覆盖: {l0['covered']} / {l0['total']}  -> {l0['coverage_rate']}%"
    )
    print(
        f"[L1] ego一跳边覆盖: {l1['covered']} / {l1['total']}  -> {l1['coverage_rate']}%"
    )
    print(
        f"[L2] ego两跳路径覆盖: {l2['covered']} / {l2['total']}  -> {l2['coverage_rate']}%"
    )

    return result


if __name__ == "__main__":
    if not MAIN_SCENE_GRAPH.exists():
        raise FileNotFoundError(f"场景图文件不存在: {MAIN_SCENE_GRAPH}")
    if not MAIN_VQA_RESULT.exists():
        raise FileNotFoundError(f"VQA结果文件不存在: {MAIN_VQA_RESULT}")

    stats = compute_multi_level_coverage(MAIN_SCENE_GRAPH, MAIN_VQA_RESULT)

    # 可选：把结果存盘
    output_dir = Path("output/coverage_analysis/vqa_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "multi_level_coverage_scene-0553_frame8.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n✓ 多级覆盖率统计已保存到: {out_path}")
