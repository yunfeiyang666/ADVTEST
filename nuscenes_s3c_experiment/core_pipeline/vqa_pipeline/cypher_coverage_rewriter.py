"""
Cypher Coverage Rewriter — 第二轮改写，让 Cypher 直接返回覆盖率元数据

核心思路:
  原始 Cypher 只返回 answer (如 obj.type, count(n) 等)。
  改写后的 Cypher 额外返回涉及的节点 unique_id 和边方向，
  这样覆盖率可以直接从查询结果计算，无需再用 regex 解析 Cypher 文本。

改写规则:
  1. 解析 MATCH 模式中的节点变量和关系变量
  2. 在 RETURN 子句中追加:
     - 每个节点变量的 unique_id  (别名 _nodeN_id)
     - 每个关系变量的 direction_8_ego (别名 _relN_dir)
  3. 保持原始 answer 语义不变
  4. 处理 count/aggregation 查询的特殊情况

使用方式:
  rewriter = CypherCoverageRewriter()
  rewritten_cypher = rewriter.rewrite(original_cypher)
  # 执行 rewritten_cypher 后，从结果中提取 _nodeN_id / _relN_dir 字段
  coverage_info = rewriter.extract_coverage_from_result(query_result)
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CoverageInfo:
    """从查询结果中提取的覆盖率信息"""
    covered_nodes: Set[str] = field(default_factory=set)
    covered_edges: Set[Tuple[str, str, str]] = field(default_factory=set)   # (source, direction, target)
    covered_2hop: Set[Tuple[str, str, str]] = field(default_factory=set)    # (n1, n2, n3)


class CypherCoverageRewriter:
    """
    Cypher 覆盖率改写器

    将 LLM 生成的 answer-only Cypher 改写为同时返回覆盖率元数据的 Cypher。
    改写是确定性的，不需要 LLM 参与。
    """

    # 覆盖率元数据字段前缀
    META_PREFIX = "_cov_"

    def rewrite(self, cypher: str) -> str:
        """
        改写 Cypher，在 RETURN 中追加覆盖率元数据

        Args:
            cypher: 原始 Cypher 查询

        Returns:
            改写后的 Cypher，RETURN 中包含 _cov_* 字段
        """
        if not cypher or not cypher.strip():
            return cypher

        try:
            # 解析变量
            node_vars = self._extract_node_variables(cypher)
            rel_vars = self._extract_relation_variables(cypher)

            if not node_vars and not rel_vars:
                logger.debug("未找到可改写的变量，返回原始查询")
                return cypher

            # 判断查询类型
            is_aggregation = self._is_aggregation_query(cypher)

            if is_aggregation:
                return self._rewrite_aggregation(cypher, node_vars, rel_vars)
            else:
                return self._rewrite_simple(cypher, node_vars, rel_vars)

        except Exception as e:
            logger.warning(f"Cypher 改写失败，返回原始查询: {e}")
            return cypher

    def extract_coverage_from_result(self, result: Any) -> CoverageInfo:
        """
        从查询结果中提取覆盖率信息

        Args:
            result: Neo4j 查询结果 (dict 或 list of dicts)

        Returns:
            CoverageInfo 包含覆盖的节点/边
        """
        info = CoverageInfo()

        if not result:
            return info

        # 标准化为记录列表
        records = self._normalize_result(result)

        for record in records:
            # 提取节点 IDs
            node_ids = []
            for key, value in record.items():
                if key.startswith(self.META_PREFIX) and key.endswith("_id"):
                    if value and isinstance(value, str):
                        info.covered_nodes.add(value)
                        node_ids.append(value)

            # 提取关系方向
            directions = []
            for key, value in record.items():
                if key.startswith(self.META_PREFIX) and key.endswith("_dir"):
                    if value and isinstance(value, str):
                        directions.append(value)

            # 构建边: 配对 (source_id, direction, target_id)
            # 假设 MATCH (a)-[r]->(b) 的变量顺序: a 在 r 前面, b 在 r 后面
            # 改写时按顺序追加: a.unique_id, r.direction_8_ego, b.unique_id
            # 所以提取时: 每3个元素构成一条边
            cov_items = []
            for key in sorted(record.keys()):
                if key.startswith(self.META_PREFIX):
                    cov_items.append((key, record[key]))

            # 按序号分组
            groups = {}
            for key, value in cov_items:
                # _cov_0_id, _cov_0_dir 等
                parts = key[len(self.META_PREFIX):].split("_", 1)
                if len(parts) == 2:
                    idx, suffix = parts
                    if idx not in groups:
                        groups[idx] = {}
                    groups[idx][suffix] = value

            # 从分组构建边
            sorted_idxs = sorted(groups.keys())
            for i, idx in enumerate(sorted_idxs):
                g = groups[idx]
                if "dir" in g and g["dir"]:
                    # 这是一个关系变量，前后应该有节点
                    src_idx = sorted_idxs[i - 1] if i > 0 else None
                    tgt_idx = sorted_idxs[i + 1] if i + 1 < len(sorted_idxs) else None

                    src_id = groups.get(src_idx, {}).get("id", "") if src_idx else ""
                    tgt_id = groups.get(tgt_idx, {}).get("id", "") if tgt_idx else ""
                    direction = g["dir"]

                    if src_id and tgt_id and direction:
                        info.covered_edges.add((src_id, direction, tgt_id))

            # 检测两跳路径: 如果有3+个节点和2+条边
            if len(node_ids) >= 3 and len(info.covered_edges) >= 2:
                edges_list = list(info.covered_edges)
                # 尝试拼接链
                for e1 in edges_list:
                    for e2 in edges_list:
                        if e1[2] == e2[0]:  # e1.target == e2.source
                            info.covered_2hop.add((e1[0], e1[2], e2[2]))

        return info

    # ========================================================================
    #  内部方法: 变量提取
    # ========================================================================

    def _extract_node_variables(self, cypher: str) -> List[Tuple[str, int]]:
        """
        提取 MATCH 模式中的节点变量名及其在原始字符串中的位置

        Returns:
            [(var_name, position_in_cypher), ...]
        """
        pattern = r'\((\w+)(?::Object|\s*\{|\))'
        matches = list(re.finditer(pattern, cypher, re.IGNORECASE))

        seen = set()
        result = []
        for m in matches:
            var = m.group(1)
            if var not in seen:
                seen.add(var)
                result.append((var, m.start()))

        return result

    def _extract_relation_variables(self, cypher: str) -> List[Tuple[str, int]]:
        """
        提取 MATCH 模式中的关系变量名及其在原始字符串中的位置

        Returns:
            [(var_name, position_in_cypher), ...]
        """
        pattern = r'\[(\w+)(?::RELATES_TO|\])'
        matches = list(re.finditer(pattern, cypher, re.IGNORECASE))

        seen = set()
        result = []
        for m in matches:
            var = m.group(1)
            if var not in seen:
                seen.add(var)
                result.append((var, m.start()))

        return result

    def _is_aggregation_query(self, cypher: str) -> bool:
        """判断是否为聚合查询 (count, sum, avg 等)"""
        return_match = re.search(r'RETURN\s+(.*?)(?:\s+LIMIT|\s+ORDER|\s*$)',
                                  cypher, re.IGNORECASE | re.DOTALL)
        if return_match:
            return_clause = return_match.group(1)
            agg_funcs = ['count(', 'sum(', 'avg(', 'min(', 'max(', 'collect(']
            return any(func in return_clause.lower() for func in agg_funcs)
        return False

    # ========================================================================
    #  改写策略
    # ========================================================================

    def _rewrite_simple(self, cypher: str, node_vars: List, rel_vars: List) -> str:
        """
        改写非聚合查询: 直接在 RETURN 中追加元数据字段

        RETURN obj.type → RETURN obj.type, ego.unique_id AS _cov_0_id, ...
        """
        # 构建追加字段
        extra_fields = self._build_extra_return_fields(node_vars, rel_vars)
        if not extra_fields:
            return cypher

        # 找到 RETURN 子句并追加
        return self._append_to_return(cypher, extra_fields)

    def _rewrite_aggregation(self, cypher: str, node_vars: List, rel_vars: List) -> str:
        """
        改写聚合查询: 用 WITH 收集元数据，然后在 RETURN 中追加

        对于 count/sum 等聚合，直接追加节点 ID 会破坏聚合语义。
        策略: 用 collect(DISTINCT ...) 收集涉及的节点 ID

        RETURN count(n) AS count
        →
        RETURN count(n) AS count,
               collect(DISTINCT ego.unique_id) AS _cov_0_ids,
               collect(DISTINCT n.unique_id) AS _cov_1_ids
        """
        extra_fields = []
        global_idx = 0

        for var_name, _ in node_vars:
            alias = f"{self.META_PREFIX}{global_idx}_ids"
            extra_fields.append(f"collect(DISTINCT {var_name}.unique_id) AS {alias}")
            global_idx += 1

        for var_name, _ in rel_vars:
            alias = f"{self.META_PREFIX}{global_idx}_dirs"
            extra_fields.append(f"collect(DISTINCT {var_name}.direction_8_ego) AS {alias}")
            global_idx += 1

        if not extra_fields:
            return cypher

        return self._append_to_return(cypher, extra_fields)

    def _build_extra_return_fields(self, node_vars: List, rel_vars: List) -> List[str]:
        """构建额外的 RETURN 字段列表，按 MATCH 模式中的出现位置交替排列"""
        fields = []
        global_idx = 0

        # 合并节点和关系变量，按在 Cypher 字符串中的位置排序
        # 这样 (ego)-[r1]->(mid)-[r2]->(tgt) 会按 ego, r1, mid, r2, tgt 顺序排列
        all_vars = []
        for var_name, pos in node_vars:
            all_vars.append(("node", var_name, pos))
        for var_name, pos in rel_vars:
            all_vars.append(("rel", var_name, pos))

        all_vars.sort(key=lambda x: x[2])  # 按在 Cypher 中的位置排序

        for var_type, var_name, _ in all_vars:
            if var_type == "node":
                alias = f"{self.META_PREFIX}{global_idx}_id"
                fields.append(f"{var_name}.unique_id AS {alias}")
            else:
                alias = f"{self.META_PREFIX}{global_idx}_dir"
                fields.append(f"{var_name}.direction_8_ego AS {alias}")
            global_idx += 1

        return fields

    def _append_to_return(self, cypher: str, extra_fields: List[str]) -> str:
        """在 RETURN 子句末尾追加字段"""
        extra_str = ", " + ", ".join(extra_fields)

        # 找到 RETURN ... 的末尾 (在 LIMIT/ORDER BY 之前)
        # 策略: 找最后一个 RETURN，在 LIMIT/ORDER BY 之前插入

        # 匹配 RETURN 到 LIMIT/ORDER BY/末尾
        return_match = re.search(
            r'(RETURN\s+.+?)(\s+LIMIT\s+|\s+ORDER\s+BY\s+|\s*$)',
            cypher, re.IGNORECASE | re.DOTALL
        )

        if return_match:
            return_part = return_match.group(1)
            after_part = return_match.group(2)
            start = return_match.start()
            end = return_match.end()

            new_return = return_part + extra_str + after_part
            rewritten = cypher[:start] + new_return + cypher[end:]
            return rewritten

        # 备选: 直接在末尾追加
        return cypher.rstrip() + extra_str

    # ========================================================================
    #  结果标准化
    # ========================================================================

    def _normalize_result(self, result: Any) -> List[Dict]:
        """将各种格式的查询结果标准化为 dict 列表"""
        if isinstance(result, list):
            if all(isinstance(r, dict) for r in result):
                return result
            return []

        if isinstance(result, dict):
            # 可能是 {success: True, data: [...]}
            data = result.get("data", result.get("records", result.get("results", [])))
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            # 单条记录
            return [result]

        return []


def rewrite_and_extract(cypher: str, query_result: Any) -> CoverageInfo:
    """
    便捷函数: 改写 Cypher 并从结果中提取覆盖率

    Usage:
        rewriter = CypherCoverageRewriter()
        rewritten = rewriter.rewrite(original_cypher)
        result = neo4j.execute(rewritten)
        coverage = rewriter.extract_coverage_from_result(result)
    """
    rewriter = CypherCoverageRewriter()
    return rewriter.extract_coverage_from_result(query_result)
