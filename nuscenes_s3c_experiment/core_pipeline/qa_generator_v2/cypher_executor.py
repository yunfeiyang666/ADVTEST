"""
Cypher Executor — Neo4j 查询执行器 + CoverageTracker 集成

职责:
  1. 管理 Neo4j 连接，导入场景图，执行 Cypher 查询
  2. 将 Cypher 查询结果转化为覆盖贡献，更新 CoverageTracker
  3. 为 LLM→Cypher Oracle 提供完整的执行链路
  4. 支持无 Neo4j 的 fallback 模式 (内存图查询)

Pipeline 中 Cypher 介入的 3 个位置:
  ① 初始覆盖率计算: enumerate_all_nodes/edges/2hop_paths
  ② 缺口采集: 查询场景图中满足缺口条件的实例
  ③ L2→L0/L1 覆盖贡献: 执行 L2 路径查询，自动提取涉及的 L0 节点和 L1 边
"""

import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field

from .cypher_integration import (
    Neo4jImporter,
    CypherTemplates,
    CypherResultParser,
    CoverageContribution,
    extract_coverage_from_path,
    build_scene_summary,
    NEO4J_SCHEMA,
    LLM_CYPHER_SYSTEM_PROMPT,
    LLM_CYPHER_USER_TEMPLATE,
    CV_VISIBLE_ATTRIBUTES,
)

logger = logging.getLogger(__name__)


# ============================================================================
#  内存图查询引擎 (Fallback — 不依赖 Neo4j)
# ============================================================================

class InMemoryGraphEngine:
    """
    纯 Python 内存图查询引擎，模拟 Neo4j Cypher 的核心查询能力。
    
    适用于:
      - 开发/测试环境 (无需安装 Neo4j)
      - 小规模场景图 (< 100 节点)
      - 快速原型验证
    """

    def __init__(self, scene_data: Dict):
        self.scene_data = scene_data
        self.nodes: Dict[str, Dict] = {}       # uid → node_data
        self.edges: List[Dict] = []             # [{source, target, direction_8, distance_bin}]
        self.edges_from: Dict[str, List[Dict]] = {}  # uid → outgoing edges
        self.edges_to: Dict[str, List[Dict]] = {}    # uid → incoming edges
        self._build_index(scene_data)

    def _build_index(self, scene_data: Dict):
        """构建内存索引"""
        for node in scene_data.get("nodes", []):
            uid = node.get("unique_id", "")
            self.nodes[uid] = {
                "unique_id": uid,
                "type": node.get("type", "unknown"),
                "status": node.get("status", "unknown"),
                "heading_class": node.get("heading_class", "unknown"),
                "visibility": node.get("visibility", "v80-100"),
                "size_class": node.get("size_class", "medium"),
            }

        for edge in scene_data.get("edges", []):
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            d8 = Neo4jImporter._extract_direction_8(edge)
            db = Neo4jImporter._extract_distance_bin(edge)
            if not src or not tgt or not d8:
                continue
            edge_record = {
                "source": src,
                "target": tgt,
                "direction_8": d8,
                "distance_bin": db,
            }
            self.edges.append(edge_record)
            self.edges_from.setdefault(src, []).append(edge_record)
            self.edges_to.setdefault(tgt, []).append(edge_record)

    # ---- 枚举查询 ----

    def enumerate_all_nodes(self) -> List[Dict]:
        """枚举所有非 ego 节点"""
        return [n for n in self.nodes.values() if n["type"] != "ego"]

    def enumerate_all_edges(self) -> List[Dict]:
        """枚举所有空间关系边"""
        return [
            {"src": e["source"], "direction": e["direction_8"],
             "tgt": e["target"], "distance_bin": e["distance_bin"]}
            for e in self.edges
        ]

    def enumerate_all_2hop_paths(self) -> List[Dict]:
        """枚举所有两跳路径: A→B→C where A≠C"""
        paths = []
        for e1 in self.edges:
            mid = e1["target"]
            for e2 in self.edges_from.get(mid, []):
                if e1["source"] != e2["target"]:
                    paths.append({
                        "n1": e1["source"], "d1": e1["direction_8"],
                        "n2": mid, "d2": e2["direction_8"],
                        "n3": e2["target"],
                    })
        return paths

    # ---- L0 查询 ----

    def query_l0_type_exist(self, target_type: str) -> List[Dict]:
        return [
            {"uid": n["unique_id"], "status": n["status"]}
            for n in self.nodes.values()
            if n["type"] == target_type
        ]

    def query_l0_object_status(self, unique_id: str) -> List[Dict]:
        node = self.nodes.get(unique_id)
        if node:
            return [{"status": node["status"], "heading": node["heading_class"]}]
        return []

    # ---- L1 查询 ----

    def query_l1_direction_exist(self, ref_id: str, direction: str,
                                  target_type: str) -> List[Dict]:
        results = []
        for e in self.edges_from.get(ref_id, []):
            if e["direction_8"] == direction:
                tgt_node = self.nodes.get(e["target"], {})
                if tgt_node.get("type") == target_type:
                    results.append({
                        "uid": tgt_node["unique_id"],
                        "status": tgt_node.get("status", ""),
                        "distance_bin": e["distance_bin"],
                    })
        return results

    def query_l1_direction_status(self, ref_id: str, direction: str) -> List[Dict]:
        results = []
        for e in self.edges_from.get(ref_id, []):
            if e["direction_8"] == direction:
                tgt_node = self.nodes.get(e["target"], {})
                results.append({
                    "uid": tgt_node.get("unique_id", ""),
                    "type": tgt_node.get("type", ""),
                    "status": tgt_node.get("status", ""),
                    "heading": tgt_node.get("heading_class", ""),
                })
        return results

    def query_l1_heading(self, ref_id: str, direction: str) -> List[Dict]:
        results = []
        for e in self.edges_from.get(ref_id, []):
            if e["direction_8"] == direction:
                tgt_node = self.nodes.get(e["target"], {})
                results.append({
                    "uid": tgt_node.get("unique_id", ""),
                    "type": tgt_node.get("type", ""),
                    "heading": tgt_node.get("heading_class", ""),
                })
        return results

    # ---- L2 查询: 严格两连边 A→B→C ----

    def query_l2_chain_exist(self, ref_id: str, dir1: str, mid_type: str,
                              dir2: str, target_type: str) -> List[Dict]:
        """链式方向存在性: ref→[dir1]→mid{type}→[dir2]→target{type}"""
        results = []
        for e1 in self.edges_from.get(ref_id, []):
            if e1["direction_8"] != dir1:
                continue
            mid_node = self.nodes.get(e1["target"], {})
            if mid_node.get("type") != mid_type:
                continue
            mid_id = mid_node["unique_id"]
            for e2 in self.edges_from.get(mid_id, []):
                if e2["direction_8"] != dir2:
                    continue
                tgt_node = self.nodes.get(e2["target"], {})
                if target_type and tgt_node.get("type") != target_type:
                    continue
                results.append({
                    "n1": ref_id, "d1": dir1,
                    "n2": mid_id, "d2": dir2,
                    "n3": tgt_node["unique_id"],
                    "target_status": tgt_node.get("status", ""),
                })
        return results

    def query_l2_chain_status(self, ref_id: str, dir1: str, mid_type: str,
                               dir2: str) -> List[Dict]:
        """链式方向状态查询"""
        results = []
        for e1 in self.edges_from.get(ref_id, []):
            if e1["direction_8"] != dir1:
                continue
            mid_node = self.nodes.get(e1["target"], {})
            if mid_type and mid_node.get("type") != mid_type:
                continue
            mid_id = mid_node["unique_id"]
            for e2 in self.edges_from.get(mid_id, []):
                if e2["direction_8"] != dir2:
                    continue
                tgt_node = self.nodes.get(e2["target"], {})
                results.append({
                    "uid": tgt_node["unique_id"],
                    "type": tgt_node.get("type", ""),
                    "status": tgt_node.get("status", ""),
                    "heading": tgt_node.get("heading_class", ""),
                    "mid_id": mid_id,
                })
        return results

    def query_l2_chain_heading(self, ref_id: str, dir1: str, mid_type: str,
                                dir2: str) -> List[Dict]:
        """链式方向朝向查询"""
        results = []
        for e1 in self.edges_from.get(ref_id, []):
            if e1["direction_8"] != dir1:
                continue
            mid_node = self.nodes.get(e1["target"], {})
            if mid_type and mid_node.get("type") != mid_type:
                continue
            mid_id = mid_node["unique_id"]
            for e2 in self.edges_from.get(mid_id, []):
                if e2["direction_8"] != dir2:
                    continue
                tgt_node = self.nodes.get(e2["target"], {})
                results.append({
                    "uid": tgt_node["unique_id"],
                    "type": tgt_node.get("type", ""),
                    "heading": tgt_node.get("heading_class", ""),
                    "mid_id": mid_id,
                })
        return results

    # ---- 覆盖贡献分析 ----

    def query_l2_coverage_contribution(self, ref_id: str, mid_id: str,
                                        target_id: str) -> List[Dict]:
        """分析一条 L2 路径对 L0/L1 的覆盖贡献"""
        ref_node = self.nodes.get(ref_id, {})
        mid_node = self.nodes.get(mid_id, {})
        tgt_node = self.nodes.get(target_id, {})

        # 找到 ref→mid 和 mid→target 的边
        d1 = ""
        for e in self.edges_from.get(ref_id, []):
            if e["target"] == mid_id:
                d1 = e["direction_8"]
                break
        d2 = ""
        for e in self.edges_from.get(mid_id, []):
            if e["target"] == target_id:
                d2 = e["direction_8"]
                break

        if not d1 or not d2:
            return []

        return [{
            "n1": ref_id, "n1_type": ref_node.get("type", ""),
            "n1_status": ref_node.get("status", ""),
            "d1": d1,
            "n2": mid_id, "n2_type": mid_node.get("type", ""),
            "n2_status": mid_node.get("status", ""),
            "d2": d2,
            "n3": target_id, "n3_type": tgt_node.get("type", ""),
            "n3_status": tgt_node.get("status", ""),
        }]


# ============================================================================
#  Cypher 执行器 (统一接口)
# ============================================================================

class CypherExecutor:
    """
    统一的 Cypher 查询执行器
    
    支持两种后端:
      - neo4j: 真实 Neo4j 数据库 (需安装 neo4j Python driver)
      - memory: InMemoryGraphEngine (无依赖, 用于开发/测试)
    """

    def __init__(self, scene_data: Dict, backend: str = "memory",
                 neo4j_uri: str = None, neo4j_auth: tuple = None):
        """
        Args:
            scene_data: 场景图数据 {"nodes": [...], "edges": [...]}
            backend: "memory" 或 "neo4j"
            neo4j_uri: Neo4j 连接地址 (仅 neo4j 后端)
            neo4j_auth: (user, password) (仅 neo4j 后端)
        """
        self.scene_data = scene_data
        self.backend = backend
        self._driver = None

        if backend == "memory":
            self._engine = InMemoryGraphEngine(scene_data)
            logger.info(f"Using InMemoryGraphEngine: "
                        f"{len(self._engine.nodes)} nodes, {len(self._engine.edges)} edges")
        elif backend == "neo4j":
            self._init_neo4j(neo4j_uri, neo4j_auth, scene_data)
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def _init_neo4j(self, uri: str, auth: tuple, scene_data: Dict):
        """初始化 Neo4j 连接并导入场景图"""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(uri, auth=auth)
            # 导入场景图
            statements = Neo4jImporter.scene_to_cypher_statements(scene_data)
            with self._driver.session() as session:
                for stmt in statements:
                    session.run(stmt)
            logger.info(f"Neo4j scene imported: {len(scene_data.get('nodes', []))} nodes")
        except ImportError:
            logger.warning("neo4j driver not installed, falling back to memory engine")
            self.backend = "memory"
            self._engine = InMemoryGraphEngine(scene_data)

    def close(self):
        """关闭 Neo4j 连接"""
        if self._driver:
            self._driver.close()

    # ---- 覆盖率枚举 (Pipeline位置①) ----

    def enumerate_nodes(self) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.enumerate_all_nodes()
        return self._run_cypher(CypherTemplates.enumerate_all_nodes())

    def enumerate_edges(self) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.enumerate_all_edges()
        return self._run_cypher(CypherTemplates.enumerate_all_edges())

    def enumerate_2hop_paths(self) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.enumerate_all_2hop_paths()
        return self._run_cypher(CypherTemplates.enumerate_all_2hop_paths())

    # ---- 缺口查询 (Pipeline位置②) ----

    def query_gap(self, gap: Dict) -> List[Dict]:
        """
        查询场景图中是否存在满足缺口条件的实例
        
        Args:
            gap: {"level": "L0"/"L1"/"L2", ...} 缺口描述
            
        Returns:
            满足条件的实例列表
        """
        level = gap.get("level", "")

        if level == "L0":
            node_id = gap.get("node_id", "")
            return self._query_l0(node_id)

        elif level == "L1":
            src = gap.get("source", "")
            direction = gap.get("direction", "")
            tgt = gap.get("target", "")
            return self._query_l1(src, direction, tgt)

        elif level == "L2":
            n1 = gap.get("node1", "")
            n2 = gap.get("node2", "")
            n3 = gap.get("node3", "")
            return self._query_l2(n1, n2, n3)

        return []

    def _query_l0(self, node_id: str) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.query_l0_object_status(node_id)
        return self._run_cypher(CypherTemplates.l0_object_status(node_id))

    def _query_l1(self, src: str, direction: str, tgt: str) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.query_l1_direction_status(src, direction)
        return self._run_cypher(CypherTemplates.l1_direction_status(src, direction))

    def _query_l2(self, n1: str, n2: str, n3: str) -> List[Dict]:
        if self.backend == "memory":
            return self._engine.query_l2_coverage_contribution(n1, n2, n3)
        return self._run_cypher(
            CypherTemplates.l2_coverage_contribution(n1, "", n2, "", n3))

    # ---- L2 覆盖贡献 (Pipeline位置③) ----

    def compute_l2_coverage_contribution(self, n1: str, n2: str,
                                          n3: str) -> CoverageContribution:
        """
        计算一条 L2 路径对 L0/L1 的覆盖贡献
        
        Returns:
            CoverageContribution 包含 l0_nodes, l1_edges, l2_paths
        """
        if self.backend == "memory":
            records = self._engine.query_l2_coverage_contribution(n1, n2, n3)
        else:
            records = self._run_cypher(
                CypherTemplates.l2_coverage_contribution(n1, "", n2, "", n3))

        if not records:
            return CoverageContribution()

        return extract_coverage_from_path(records[0])

    # ---- Neo4j 查询执行 ----

    def _run_cypher(self, cypher: str, params: Dict = None) -> List[Dict]:
        """执行 Cypher 查询并返回结果"""
        if not self._driver:
            logger.warning("No Neo4j driver, returning empty results")
            return []

        try:
            with self._driver.session() as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Cypher execution error: {e}")
            return []

    # ---- LLM→Cypher Oracle ----

    def execute_llm_cypher(self, question: str, llm_client=None) -> Tuple[List[Dict], str]:
        """
        LLM→Cypher Oracle: 自然语言问题 → Cypher → 执行 → 结果
        
        Args:
            question: 自然语言问题
            llm_client: LLM 客户端 (需有 chat() 方法)
            
        Returns:
            (query_results, cypher_query_string)
        """
        if llm_client is None:
            logger.warning("No LLM client provided for Cypher generation")
            return [], ""

        # 构建 prompt
        scene_summary = build_scene_summary(self.scene_data)
        system_prompt = LLM_CYPHER_SYSTEM_PROMPT.format(schema=NEO4J_SCHEMA)
        user_prompt = LLM_CYPHER_USER_TEMPLATE.format(
            scene_summary=scene_summary,
            question=question,
        )

        # 调用 LLM 生成 Cypher
        try:
            response = llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            cypher = self._extract_cypher(response)
            logger.info(f"LLM generated Cypher: {cypher[:100]}...")

            # 执行 Cypher
            if self.backend == "neo4j":
                results = self._run_cypher(cypher)
            else:
                logger.warning("LLM-generated Cypher requires Neo4j backend; "
                               "memory engine cannot execute arbitrary Cypher")
                results = []

            return results, cypher

        except Exception as e:
            logger.error(f"LLM→Cypher error: {e}")
            return [], ""

    @staticmethod
    def _extract_cypher(llm_response: str) -> str:
        """从 LLM 响应中提取 Cypher 查询"""
        # 尝试从 code block 中提取
        if "```cypher" in llm_response:
            start = llm_response.index("```cypher") + len("```cypher")
            end = llm_response.index("```", start)
            return llm_response[start:end].strip()
        if "```" in llm_response:
            start = llm_response.index("```") + 3
            end = llm_response.index("```", start)
            return llm_response[start:end].strip()
        # 整个响应就是 Cypher
        return llm_response.strip()

    # ---- 场景摘要 ----

    def get_scene_summary(self) -> str:
        """获取场景摘要"""
        return build_scene_summary(self.scene_data)

    def get_schema(self) -> str:
        """获取 Neo4j schema"""
        return NEO4J_SCHEMA
