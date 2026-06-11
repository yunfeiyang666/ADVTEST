"""
Unified Coverage Tracker — 统一覆盖率追踪器

三组 KV map (L0 / L1 / L2)，JSON 持久化，hash 优化 O(1) 查询。

覆盖维度:
  L0  节点覆盖: key = node_id
      → 该对象是否被任何问题涉及
  L1  边覆盖:   key = (source, direction_8, target)
      → 该空间关系是否被问过
  L2  两跳路径: key = (node1, node2, node3)
      → 该两跳路径是否被覆盖

每条覆盖记录包含:
  - hit_count:    被覆盖次数
  - template_ids: 使用过的模板 ID 列表
  - question_ids: 对应的题目 ID 列表

用法:
    tracker = CoverageTracker.from_scene_graph(scene_data)
    tracker.record_l0("car_1", template_id="L0_exist_A1", question_id="q001")
    tracker.record_l1("ego", "front", "car_1", ...)
    tracker.save("coverage.json")
    tracker2 = CoverageTracker.load("coverage.json")
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict


# ============================================================================
#  覆盖记录
# ============================================================================

@dataclass
class CoverageRecord:
    """单条覆盖记录"""
    hit_count: int = 0
    template_ids: List[str] = field(default_factory=list)
    question_ids: List[str] = field(default_factory=list)

    def record(self, template_id: str = "", question_id: str = ""):
        self.hit_count += 1
        if template_id and template_id not in self.template_ids:
            self.template_ids.append(template_id)
        if question_id and question_id not in self.question_ids:
            self.question_ids.append(question_id)

    @property
    def is_covered(self) -> bool:
        return self.hit_count > 0

    def to_dict(self) -> Dict:
        return {"hit_count": self.hit_count,
                "template_ids": self.template_ids,
                "question_ids": self.question_ids}

    @staticmethod
    def from_dict(d: Dict) -> 'CoverageRecord':
        return CoverageRecord(
            hit_count=d.get("hit_count", 0),
            template_ids=d.get("template_ids", []),
            question_ids=d.get("question_ids", []),
        )


# ============================================================================
#  Hash 工具
# ============================================================================

def _hash_key(*parts: str) -> str:
    """将多段字符串拼接后取 SHA-256 前 16 位作为 hash key"""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _edge_key(source: str, direction: str, target: str) -> str:
    return f"{source}|{direction}|{target}"


def _path_key(n1: str, n2: str, n3: str) -> str:
    return f"{n1}|{n2}|{n3}"


# ============================================================================
#  统一覆盖率追踪器
# ============================================================================

class CoverageTracker:
    """
    统一覆盖率追踪器

    内部存储:
      _l0: Dict[str, CoverageRecord]   key = node_id
      _l1: Dict[str, CoverageRecord]   key = "source|direction|target"
      _l2: Dict[str, CoverageRecord]   key = "n1|n2|n3"

    hash 索引 (可选, 用于大规模场景加速):
      _l0_hash: Dict[hash_key, str]    hash -> node_id
      _l1_hash: Dict[hash_key, str]    hash -> edge_key
      _l2_hash: Dict[hash_key, str]    hash -> path_key
    """

    def __init__(self):
        # 三组 KV map
        self._l0: Dict[str, CoverageRecord] = {}
        self._l1: Dict[str, CoverageRecord] = {}
        self._l2: Dict[str, CoverageRecord] = {}

        # hash 反查索引
        self._l0_hash: Dict[str, str] = {}
        self._l1_hash: Dict[str, str] = {}
        self._l2_hash: Dict[str, str] = {}

        # 元数据
        self.scene_name: str = ""
        self.frame_idx: int = 0
        self.total_nodes: int = 0
        self.total_edges: int = 0
        self.total_2hop: int = 0

    # ====================================================================
    #  初始化: 从场景图构建所有可能的覆盖元素
    # ====================================================================

    @classmethod
    def from_scene_graph(cls, scene_data: Dict) -> 'CoverageTracker':
        """从场景图数据初始化 (所有元素初始为未覆盖)"""
        tracker = cls()
        tracker.scene_name = scene_data.get("scene_name", "")
        tracker.frame_idx = scene_data.get("frame_idx", 0)

        nodes = scene_data.get("nodes", [])
        edges = scene_data.get("edges", [])

        # L0: 注册所有非 ego 节点
        for node in nodes:
            uid = node.get("unique_id", "")
            if uid and uid != "ego":
                tracker._register_l0(uid)

        # L1: 注册所有边
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            d8 = cls._extract_direction_8(edge)
            if src and tgt and d8:
                tracker._register_l1(src, d8, tgt)

        # L2: 注册所有两跳路径
        edges_from: Dict[str, List[Dict]] = defaultdict(list)
        for edge in edges:
            src = edge.get("source", "")
            edges_from[src].append(edge)

        for edge1 in edges:
            mid = edge1.get("target", "")
            src = edge1.get("source", "")
            for edge2 in edges_from.get(mid, []):
                tgt = edge2.get("target", "")
                if tgt and tgt != src:
                    tracker._register_l2(src, mid, tgt)

        tracker.total_nodes = len(tracker._l0)
        tracker.total_edges = len(tracker._l1)
        tracker.total_2hop = len(tracker._l2)

        return tracker

    # ====================================================================
    #  注册 (内部)
    # ====================================================================

    def _register_l0(self, node_id: str):
        if node_id not in self._l0:
            self._l0[node_id] = CoverageRecord()
            h = _hash_key(node_id)
            self._l0_hash[h] = node_id

    def _register_l1(self, source: str, direction: str, target: str):
        key = _edge_key(source, direction, target)
        if key not in self._l1:
            self._l1[key] = CoverageRecord()
            h = _hash_key(source, direction, target)
            self._l1_hash[h] = key

    def _register_l2(self, n1: str, n2: str, n3: str):
        key = _path_key(n1, n2, n3)
        if key not in self._l2:
            self._l2[key] = CoverageRecord()
            h = _hash_key(n1, n2, n3)
            self._l2_hash[h] = key

    # ====================================================================
    #  记录覆盖
    # ====================================================================

    def record_l0(self, node_id: str,
                  template_id: str = "", question_id: str = ""):
        """记录 L0 节点覆盖"""
        if node_id not in self._l0:
            self._register_l0(node_id)
        self._l0[node_id].record(template_id, question_id)

    def record_l1(self, source: str, direction: str, target: str,
                  template_id: str = "", question_id: str = ""):
        """记录 L1 边覆盖"""
        key = _edge_key(source, direction, target)
        if key not in self._l1:
            self._register_l1(source, direction, target)
        self._l1[key].record(template_id, question_id)

    def record_l2(self, n1: str, n2: str, n3: str,
                  template_id: str = "", question_id: str = ""):
        """记录 L2 两跳路径覆盖"""
        key = _path_key(n1, n2, n3)
        if key not in self._l2:
            self._register_l2(n1, n2, n3)
        self._l2[key].record(template_id, question_id)

    def record_from_qa(self, qa: Dict):
        """
        从生成的 QA dict 自动记录覆盖

        qa 格式 (兼容 GeneratedQA / CoverageDrivenTemplateGenerator 输出):
          - covered_elements: [node_id, ...]
          - template_id: str
          - coverage_level: "L0" / "L1" / "L2"
          - params: {source, direction, target, ...}  (for L1/L2)
        """
        tid = qa.get("template_id", "")
        qid = qa.get("question_id", "")
        level = qa.get("coverage_level", "")

        # 覆盖涉及的节点 (L0)
        for elem in qa.get("covered_elements", []):
            self.record_l0(elem, tid, qid)

        # L1 边覆盖
        params = qa.get("params", {})
        if level == "L1" or params.get("direction"):
            src = params.get("ref_id", params.get("source", ""))
            tgt = params.get("obj_id", params.get("target", ""))
            d = params.get("direction", "")
            if src and tgt and d:
                self.record_l1(src, d, tgt, tid, qid)

        # L2 路径覆盖 (同时记录两条 L1 边 — 跨级附带覆盖)
        if level == "L2":
            n1 = params.get("ref_id", params.get("node1", ""))
            n2 = params.get("mid_id", params.get("node2", ""))
            n3 = params.get("target_id", params.get("node3", ""))
            if n1 and n2 and n3:
                self.record_l2(n1, n2, n3, tid, qid)
                # 附带覆盖两条 L1 边: n1→n2 和 n2→n3
                d1 = params.get("direction2", params.get("direction", ""))
                d2 = params.get("direction1", "")
                if n1 and n2 and d1:
                    self.record_l1(n1, d1, n2, tid, qid)
                if n2 and n3 and d2:
                    self.record_l1(n2, d2, n3, tid, qid)

    # ====================================================================
    #  查询接口
    # ====================================================================

    def get_l0(self, node_id: str) -> Optional[CoverageRecord]:
        return self._l0.get(node_id)

    def get_l1(self, source: str, direction: str, target: str) -> Optional[CoverageRecord]:
        return self._l1.get(_edge_key(source, direction, target))

    def get_l2(self, n1: str, n2: str, n3: str) -> Optional[CoverageRecord]:
        return self._l2.get(_path_key(n1, n2, n3))

    def get_l0_by_hash(self, h: str) -> Optional[CoverageRecord]:
        key = self._l0_hash.get(h)
        return self._l0.get(key) if key else None

    def get_l1_by_hash(self, h: str) -> Optional[CoverageRecord]:
        key = self._l1_hash.get(h)
        return self._l1.get(key) if key else None

    def get_l2_by_hash(self, h: str) -> Optional[CoverageRecord]:
        key = self._l2_hash.get(h)
        return self._l2.get(key) if key else None

    def is_l0_covered(self, node_id: str) -> bool:
        rec = self._l0.get(node_id)
        return rec.is_covered if rec else False

    def is_l1_covered(self, source: str, direction: str, target: str) -> bool:
        rec = self._l1.get(_edge_key(source, direction, target))
        return rec.is_covered if rec else False

    def is_l2_covered(self, n1: str, n2: str, n3: str) -> bool:
        rec = self._l2.get(_path_key(n1, n2, n3))
        return rec.is_covered if rec else False

    # ====================================================================
    #  缺口提取
    # ====================================================================

    def uncovered_l0(self) -> List[str]:
        """返回未覆盖的 L0 节点 ID 列表"""
        return [k for k, v in self._l0.items() if not v.is_covered]

    def uncovered_l1(self) -> List[Tuple[str, str, str]]:
        """返回未覆盖的 L1 边 (source, direction, target) 列表"""
        result = []
        for k, v in self._l1.items():
            if not v.is_covered:
                parts = k.split("|")
                if len(parts) == 3:
                    result.append((parts[0], parts[1], parts[2]))
        return result

    def uncovered_l2(self) -> List[Tuple[str, str, str]]:
        """返回未覆盖的 L2 路径 (n1, n2, n3) 列表"""
        result = []
        for k, v in self._l2.items():
            if not v.is_covered:
                parts = k.split("|")
                if len(parts) == 3:
                    result.append((parts[0], parts[1], parts[2]))
        return result

    def gaps_as_list(self) -> List[Dict]:
        """
        返回所有缺口，格式兼容 CoverageDrivenTemplateGenerator

        Returns:
            [{"level": "L0", "node_id": ...},
             {"level": "L1", "source": ..., "target": ..., "direction": ...},
             {"level": "L2", "node1": ..., "node2": ..., "node3": ...}]
        """
        gaps = []
        for nid in self.uncovered_l0():
            gaps.append({"level": "L0", "node_id": nid})
        for src, d, tgt in self.uncovered_l1():
            gaps.append({"level": "L1", "source": src, "target": tgt, "direction": d})
        for n1, n2, n3 in self.uncovered_l2():
            gaps.append({"level": "L2", "node1": n1, "node2": n2, "node3": n3})
        return gaps

    # ====================================================================
    #  覆盖率统计
    # ====================================================================

    def coverage_rates(self) -> Dict[str, Any]:
        """计算 L0/L1/L2 覆盖率"""
        l0_covered = sum(1 for v in self._l0.values() if v.is_covered)
        l1_covered = sum(1 for v in self._l1.values() if v.is_covered)
        l2_covered = sum(1 for v in self._l2.values() if v.is_covered)

        l0_total = max(len(self._l0), 1)
        l1_total = max(len(self._l1), 1)
        l2_total = max(len(self._l2), 1)

        return {
            "L0": l0_covered / l0_total,
            "L1": l1_covered / l1_total,
            "L2": l2_covered / l2_total,
            "L0_detail": {"covered": l0_covered, "total": len(self._l0)},
            "L1_detail": {"covered": l1_covered, "total": len(self._l1)},
            "L2_detail": {"covered": l2_covered, "total": len(self._l2)},
        }

    def template_distribution(self) -> Dict[str, int]:
        """统计各模板被使用的次数"""
        dist: Dict[str, int] = defaultdict(int)
        for maps in [self._l0, self._l1, self._l2]:
            for rec in maps.values():
                for tid in rec.template_ids:
                    dist[tid] += 1
        return dict(dist)

    def summary(self) -> Dict[str, Any]:
        """综合统计"""
        rates = self.coverage_rates()
        return {
            "scene_name": self.scene_name,
            "frame_idx": self.frame_idx,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "total_2hop": self.total_2hop,
            "coverage_rates": rates,
            "uncovered_l0_count": len(self.uncovered_l0()),
            "uncovered_l1_count": len(self.uncovered_l1()),
            "uncovered_l2_count": len(self.uncovered_l2()),
            "total_questions": sum(v.hit_count for v in self._l0.values()),
            "template_distribution": self.template_distribution(),
        }

    def print_summary(self):
        """打印覆盖率摘要"""
        s = self.summary()
        rates = s["coverage_rates"]
        print("=" * 60)
        print(f"  Coverage Tracker — {s['scene_name']} frame {s['frame_idx']}")
        print("=" * 60)
        print(f"  L0 节点覆盖: {rates['L0']:.1%}  "
              f"({rates['L0_detail']['covered']}/{rates['L0_detail']['total']})")
        print(f"  L1 边覆盖:   {rates['L1']:.1%}  "
              f"({rates['L1_detail']['covered']}/{rates['L1_detail']['total']})")
        print(f"  L2 路径覆盖: {rates['L2']:.1%}  "
              f"({rates['L2_detail']['covered']}/{rates['L2_detail']['total']})")
        print(f"  未覆盖: L0={s['uncovered_l0_count']}, "
              f"L1={s['uncovered_l1_count']}, L2={s['uncovered_l2_count']}")
        print(f"  总题数:  {s['total_questions']}")
        td = s["template_distribution"]
        if td:
            print(f"  模板种类: {len(td)}")
            top5 = sorted(td.items(), key=lambda x: -x[1])[:5]
            for tid, cnt in top5:
                print(f"    {tid}: {cnt}")

    # ====================================================================
    #  JSON 持久化
    # ====================================================================

    def save(self, path: str):
        """保存到 JSON 文件"""
        data = {
            "meta": {
                "scene_name": self.scene_name,
                "frame_idx": self.frame_idx,
                "total_nodes": self.total_nodes,
                "total_edges": self.total_edges,
                "total_2hop": self.total_2hop,
            },
            "l0": {k: v.to_dict() for k, v in self._l0.items()},
            "l1": {k: v.to_dict() for k, v in self._l1.items()},
            "l2": {k: v.to_dict() for k, v in self._l2.items()},
        }
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> 'CoverageTracker':
        """从 JSON 文件加载"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tracker = cls()
        meta = data.get("meta", {})
        tracker.scene_name = meta.get("scene_name", "")
        tracker.frame_idx = meta.get("frame_idx", 0)
        tracker.total_nodes = meta.get("total_nodes", 0)
        tracker.total_edges = meta.get("total_edges", 0)
        tracker.total_2hop = meta.get("total_2hop", 0)

        for k, v in data.get("l0", {}).items():
            tracker._l0[k] = CoverageRecord.from_dict(v)
            tracker._l0_hash[_hash_key(k)] = k

        for k, v in data.get("l1", {}).items():
            tracker._l1[k] = CoverageRecord.from_dict(v)
            parts = k.split("|")
            if len(parts) == 3:
                tracker._l1_hash[_hash_key(*parts)] = k

        for k, v in data.get("l2", {}).items():
            tracker._l2[k] = CoverageRecord.from_dict(v)
            parts = k.split("|")
            if len(parts) == 3:
                tracker._l2_hash[_hash_key(*parts)] = k

        return tracker

    # ====================================================================
    #  兼容 CoverageDrivenTemplateGenerator 的接口
    # ====================================================================

    def to_coverage_stats_dict(self) -> Dict:
        """
        导出为兼容 CoverageDrivenTemplateGenerator 的 coverage_stats dict

        返回:
            {
                "covered_nodes": [node_id, ...],
                "covered_edges": [(src, dir, tgt), ...],
                "covered_2hop_paths": [(n1, n2, n3), ...],
            }
        """
        covered_nodes = [k for k, v in self._l0.items() if v.is_covered]
        covered_edges = []
        for k, v in self._l1.items():
            if v.is_covered:
                parts = k.split("|")
                if len(parts) == 3:
                    covered_edges.append(tuple(parts))
        covered_paths = []
        for k, v in self._l2.items():
            if v.is_covered:
                parts = k.split("|")
                if len(parts) == 3:
                    covered_paths.append(tuple(parts))

        return {
            "covered_nodes": covered_nodes,
            "covered_edges": covered_edges,
            "covered_2hop_paths": covered_paths,
        }

    # ====================================================================
    #  静态工具
    # ====================================================================

    # ====================================================================
    #  桥接 UnifiedCoverageStats
    # ====================================================================

    @classmethod
    def from_unified(cls, unified, scene_data: Dict = None) -> 'CoverageTracker':
        """
        从 coverage_loop.unified_coverage.UnifiedCoverageStats 转换

        Args:
            unified: UnifiedCoverageStats 实例或其 to_dict() 输出
            scene_data: 场景图数据 (可选, 用于注册全量元素)
        """
        if scene_data:
            tracker = cls.from_scene_graph(scene_data)
        else:
            tracker = cls()

        # 处理 dataclass 实例
        if hasattr(unified, 'covered_nodes'):
            tracker.scene_name = getattr(unified, 'scene_name', '')
            tracker.frame_idx = getattr(unified, 'frame_idx', 0)
            for nid in unified.covered_nodes:
                count = unified.node_coverage_count.get(nid, 1)
                for _ in range(count):
                    tracker.record_l0(nid)
            for edge_tuple in unified.covered_edges:
                if len(edge_tuple) == 3:
                    src, d, tgt = edge_tuple
                    count = unified.edge_coverage_count.get(
                        f"{src}-{d}->{tgt}", 1)
                    for _ in range(count):
                        tracker.record_l1(src, d, tgt)
            for path_tuple in getattr(unified, 'covered_2hop_paths', set()):
                if len(path_tuple) == 3:
                    tracker.record_l2(*path_tuple)
        # 处理 dict
        elif isinstance(unified, dict):
            tracker.scene_name = unified.get('scene_name', '')
            tracker.frame_idx = unified.get('frame_idx', 0)
            cov = unified.get('coverage', {})
            for nid in cov.get('L0', {}).get('nodes', []):
                tracker.record_l0(nid)
            for edge_key, cnt in unified.get('edge_coverage_count', {}).items():
                parts = edge_key.replace('->', '-').split('-')
                if len(parts) >= 3:
                    src, d, tgt = parts[0], parts[1], parts[-1]
                    for _ in range(cnt):
                        tracker.record_l1(src, d, tgt)

        return tracker

    def to_unified(self):
        """
        转换为 UnifiedCoverageStats 实例

        Returns:
            UnifiedCoverageStats
        """
        from ..coverage_loop.unified_coverage import UnifiedCoverageStats
        stats = UnifiedCoverageStats()
        stats.scene_name = self.scene_name
        stats.frame_idx = self.frame_idx
        stats.total_nodes = self.total_nodes
        stats.total_edges = self.total_edges
        stats.total_2hop_paths = self.total_2hop

        for nid, rec in self._l0.items():
            if rec.is_covered:
                stats.covered_nodes.add(nid)
                stats.node_coverage_count[nid] = rec.hit_count

        for key, rec in self._l1.items():
            if rec.is_covered:
                parts = key.split('|')
                if len(parts) == 3:
                    stats.covered_edges.add(tuple(parts))
                    stats.edge_coverage_count[
                        f"{parts[0]}-{parts[1]}->{parts[2]}"] = rec.hit_count

        for key, rec in self._l2.items():
            if rec.is_covered:
                parts = key.split('|')
                if len(parts) == 3:
                    stats.covered_2hop_paths.add(tuple(parts))

        stats.total_questions = sum(v.hit_count for v in self._l0.values())
        return stats

    @staticmethod
    def _extract_direction_8(edge: Dict) -> Optional[str]:
        """从边提取 direction_8"""
        if "direction_8" in edge:
            return edge["direction_8"]
        metrics = edge.get("metrics", {})
        if isinstance(metrics, dict):
            ds = metrics.get("direction_source", {})
            if isinstance(ds, dict):
                return ds.get("direction_8")
            de = metrics.get("direction_ego", {})
            if isinstance(de, dict):
                return de.get("direction_8")
            # 直接取 direction_8
            if "direction_8" in metrics:
                return metrics["direction_8"]
        return None


# ============================================================================
#  快捷工厂函数
# ============================================================================

def create_tracker_from_scene_graph_file(path: str) -> CoverageTracker:
    """从场景图 JSON 文件创建 tracker"""
    with open(path, "r", encoding="utf-8") as f:
        scene_data = json.load(f)
    return CoverageTracker.from_scene_graph(scene_data)


# ============================================================================
#  演示 / 自测
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sg_path = sys.argv[1]
        print(f"从场景图加载: {sg_path}")
        tracker = create_tracker_from_scene_graph_file(sg_path)
    else:
        # 构造一个最小示例
        demo_scene = {
            "scene_name": "demo",
            "frame_idx": 0,
            "nodes": [
                {"unique_id": "ego", "type": "ego", "status": "stopped"},
                {"unique_id": "car_1", "type": "car", "status": "moving"},
                {"unique_id": "car_2", "type": "car", "status": "stopped"},
                {"unique_id": "ped_1", "type": "pedestrian", "status": "moving"},
            ],
            "edges": [
                {"source": "ego", "target": "car_1",
                 "metrics": {"direction_8": "front", "distance": 5.0}},
                {"source": "ego", "target": "car_2",
                 "metrics": {"direction_8": "rear", "distance": 10.0}},
                {"source": "ego", "target": "ped_1",
                 "metrics": {"direction_8": "front-left", "distance": 8.0}},
                {"source": "car_1", "target": "ped_1",
                 "metrics": {"direction_8": "left", "distance": 6.0}},
            ],
        }
        tracker = CoverageTracker.from_scene_graph(demo_scene)

    print("\n--- 初始状态 ---")
    tracker.print_summary()

    # 模拟记录一些覆盖
    tracker.record_l0("car_1", template_id="L0_exist_A1", question_id="q001")
    tracker.record_l1("ego", "front", "car_1",
                      template_id="L1_exist_A1", question_id="q002")

    print("\n--- 记录覆盖后 ---")
    tracker.print_summary()

    # 测试保存/加载
    save_path = "output/coverage_demo.json"
    tracker.save(save_path)
    print(f"\n已保存到: {save_path}")

    loaded = CoverageTracker.load(save_path)
    print("\n--- 从 JSON 加载后 ---")
    loaded.print_summary()

    # 测试 hash 查询
    import hashlib
    h = _hash_key("car_1")
    rec = loaded.get_l0_by_hash(h)
    print(f"\nhash 查询 car_1 (hash={h}): hit_count={rec.hit_count if rec else 'N/A'}")

    # 测试兼容接口
    compat = loaded.to_coverage_stats_dict()
    print(f"\n兼容接口: covered_nodes={compat['covered_nodes']}")
    print(f"兼容接口: covered_edges={compat['covered_edges']}")

    # 测试缺口提取
    gaps = loaded.gaps_as_list()
    print(f"\n缺口总数: {len(gaps)}")
    for g in gaps[:5]:
        print(f"  {g}")
