import json
import re
import logging
from typing import List, Dict, Tuple, Optional, Set
from neo4j import GraphDatabase, Driver

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SceneGraphEvaluator:
    def __init__(self, uri: str = "bolt://localhost:7600", 
                 user: str = "neo4j", 
                 password: str = "12345678"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        if self.driver:
            self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def calculate_edge_coverage(self, questions: List[Dict], edge_type: str = None) -> Tuple[int, int, float]:
        """
        计算覆盖率的核心函数
        
        Args:
            questions: 问题列表
            edge_type: 指定统计的边类型（如 'RELATES_TO'），None 表示统计所有边
        """
        covered_edge_ids = set()
        
        with self.driver.session() as session:
            # 1. 获取分母：总边数
            # 如果指定了类型，使用 [r:TYPE]，否则使用 [r]
            rel_pattern = f":{edge_type}" if edge_type else ""
            count_query = f"MATCH ()-[r{rel_pattern}]->() RETURN count(r) AS total"
            
            try:
                result = session.run(count_query)
                total_edges = result.single()['total']
                logger.info(f"图谱中总边数 (Total Edges): {total_edges}")
            except Exception as e:
                logger.error(f"获取总边数失败: {e}")
                return 0, 0, 0.0

            if total_edges == 0:
                return 0, 0, 0.0

            # 2. 获取分子：遍历问题，收集覆盖的边ID
            for idx, q in enumerate(questions):
                cypher = q.get('cypher_query', '').strip()
                if not cypher:
                    continue

                # 动态修改查询以返回关系ID
                modified_query, rel_var = self._inject_return_statement(cypher)
                
                if not modified_query:
                    # 无法注入（可能查询没用变量名，如 ()-[:REL]->()），跳过
                    continue

                try:
                    result = session.run(modified_query)
                    # 消费结果，提取ID
                    for record in result:
                        rel_obj = record.get(rel_var)
                        if rel_obj and hasattr(rel_obj, 'id'):
                            covered_edge_ids.add(rel_obj.id)
                        elif rel_obj and isinstance(rel_obj, int):
                             # 某些旧版本驱动可能直接返回ID
                            covered_edge_ids.add(rel_obj)
                            
                except Exception as e:
                    logger.warning(f"问题 ID {idx} 执行失败: {e}")
                    continue

        # 3. 计算结果
        covered_count = len(covered_edge_ids)
        coverage_rate = (covered_count / total_edges) * 100
        
        return covered_count, total_edges, round(coverage_rate, 2)

    def _inject_return_statement(self, cypher: str) -> Tuple[Optional[str], Optional[str]]:
        """
        核心辅助函数：修改 Cypher 语句，强行让它返回关系的 ID
        Returns: (修改后的查询, 关系变量名)
        """
        # 正则解析：寻找 -[r:TYPE]-> 或 -[r]-> 中的变量 r
        # Group 1: 变量名 (r)
        # Group 2: 可选的类型定义 (:TYPE)
        pattern = re.compile(r'-\[\s*(\w+)\s*(:[^\]]*)?\s*\]->')
        
        matches = pattern.findall(cypher)
        if not matches:
            return None, None

        # 默认取第一个找到的关系变量（假设它是主要考察对象）
        rel_var = matches[0][0] 

        # 检查是否已有 RETURN
        if re.search(r'\bRETURN\b', cypher, re.IGNORECASE):
            # 在 RETURN 后插入变量
            # 例如: "RETURN n, m" -> "RETURN r, n, m"
            modified_query = re.sub(
                r'(\bRETURN\s+)', 
                f'\\1{rel_var}, ', 
                cypher, 
                count=1, 
                flags=re.IGNORECASE
            )
        else:
            # 没有 RETURN，直接追加
            modified_query = f"{cypher} RETURN {rel_var}"
            
        return modified_query, rel_var

# --- 离线简化模式 (保持轻量) ---
def calculate_coverage_offline(questions: List[Dict], scene_graph_path: str) -> Tuple[int, int, float]:
    """基于 JSON 文件的近似计算"""
    try:
        with open(scene_graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            edges = data.get('edges', [])
    except FileNotFoundError:
        logger.error("场景图文件未找到")
        return 0, 0, 0.0

    total = len(edges)
    if total == 0: return 0, 0, 0.0
    
    covered_indices = set()
    
    # 预编译正则提高效率
    re_uid = re.compile(r"unique_id\s*[:=]\s*['\"](\w+)['\"]")
    re_type = re.compile(r"type\s*[:=]\s*['\"](\w+)['\"]")

    for q in questions:
        # 兼容两种字段名：cypher_query 或 cypher
        cypher = q.get('cypher_query', q.get('cypher', '')).strip()
        if not cypher: continue
        
        # 提取关键信息
        uids = set(re_uid.findall(cypher))
        types = set(t.lower() for t in re_type.findall(cypher))
        has_ego = 'ego' in cypher.lower()

        # 遍历边进行匹配 (O(N*M) 复杂度，注意性能)
        for i, edge in enumerate(edges):
            src, dst = edge.get('source', ''), edge.get('target', '')
            
            # 命中规则 1: Unique ID 匹配
            if uids and any(uid in src or uid in dst for uid in uids):
                covered_indices.add(i)
                continue
            
            # 命中规则 2: Ego 匹配
            if has_ego and src == 'ego':
                covered_indices.add(i)
                continue

            # 命中规则 3: 类型匹配 (最宽泛)
            if types:
                if any(t in src.lower() or t in dst.lower() for t in types):
                    covered_indices.add(i)

    rate = (len(covered_indices) / total) * 100
    return len(covered_indices), total, round(rate, 2)

# --- 使用示例 ---
if __name__ == '__main__':
    # 模拟数据
    mock_questions = [
        {"cypher_query": "MATCH (n:Object)-[r:RELATES_TO]->(m) WHERE n.type='car' RETURN n"},
        {"cypher_query": "MATCH (ego)-[rel]->(target) WHERE target.id='c_1' RETURN target"}
    ]
    
    # 1. 在线模式示例
    print("--- Online Mode (Neo4j) ---")
    try:
        # 使用 Context Manager 自动关闭连接
        with SceneGraphEvaluator(uri="bolt://localhost:7600", password="your_password") as evaluator:
            cov, tot, rate = evaluator.calculate_edge_coverage(mock_questions)
            print(f"Covered: {cov}/{tot} ({rate}%)")
    except Exception as e:
        print(f"Neo4j connection skipped: {e}")

    # 2. 离线模式示例
    print("\n--- Offline Mode (JSON) ---")
    # 假设有一个 dummy json
    # cov, tot, rate = calculate_coverage_offline(mock_questions, "scene.json")