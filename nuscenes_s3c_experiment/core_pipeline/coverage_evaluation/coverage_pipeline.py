"""
覆盖率评估 Pipeline (Neo4j版) - 最终优化版

流程:
1. 加载场景图 → 导入Neo4j
2. 复用VQA pipeline的LLM生成Cypher
3. 执行Cypher，提取命中的节点/边 (支持参数化查询与智能Fallback)
4. 统计覆盖率

覆盖率定义:
- L=0 (节点覆盖): 题目涉及了哪些对象节点
- L=1 (边覆盖): 题目涉及了哪些边 (关系边 + 属性边)
- L=2 (两跳路径覆盖): 题目涉及了哪些连续两条边的路径
"""

import json
import re
import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager

# 添加父目录到path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============ 配置 ============
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7600')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', '87017563')


# ============ 数据结构 ============
@dataclass
class CoverageStats:
    """覆盖率统计"""
    total_nodes: int = 0
    total_edges: int = 0
    total_2hop_paths: int = 0
    
    covered_nodes: Set[str] = field(default_factory=set)
    covered_edges: Set[Tuple[str, str]] = field(default_factory=set)
    covered_2hop_paths: Set[Tuple[str, str, str]] = field(default_factory=set)
    
    total_questions: int = 0
    analyzed_questions: int = 0
    failed_questions: int = 0
    
    def get_rates(self) -> Dict[str, float]:
        return {
            'L0': len(self.covered_nodes) / max(self.total_nodes, 1),
            'L1': len(self.covered_edges) / max(self.total_edges, 1),
            'L2': len(self.covered_2hop_paths) / max(self.total_2hop_paths, 1),
        }


# ============ Neo4j客户端 ============
class Neo4jClient:
    """Neo4j数据库客户端 (支持参数化查询)"""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self.driver = None
        self._connected = False
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def connect(self) -> bool:
        if self._connected and self.driver:
            return True
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            self._connected = True
            logger.info(f"Neo4j已连接: {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Neo4j连接失败: {e}")
            return False
    
    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            self._connected = False
    
    @contextmanager
    def session(self):
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(self, cypher: str, parameters: Dict = None) -> Dict[str, Any]:
        """执行Cypher查询 (支持参数化)"""
        if not self._connected:
            if not self.connect():
                return {"success": False, "error": "未连接", "data": [], "count": 0}
        try:
            with self.session() as session:
                result = session.run(cypher, parameters=parameters)
                records = list(result)
                data = [self._record_to_dict(r) for r in records]
                return {"success": True, "count": len(data), "data": data}
        except Exception as e:
            return {"success": False, "error": str(e), "data": [], "count": 0}
    
    def _record_to_dict(self, record) -> dict:
        row = {}
        for key in record.keys():
            val = record[key]
            if val is None:
                row[key] = None
            elif isinstance(val, (int, float, str, bool)):
                row[key] = val
            elif isinstance(val, list):
                row[key] = val
            elif hasattr(val, 'items'):
                # 处理Node/Relationship对象
                data = dict(val.items())
                # 尝试保留element_id或id以便后续处理
                if hasattr(val, 'element_id'):
                    data['_element_id'] = val.element_id
                row[key] = data
            else:
                row[key] = str(val)
        return row
    
    def clear_database(self):
        logger.info("清空Neo4j数据库...")
        with self.session() as session:
            while True:
                result = session.run("MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(n) as deleted")
                if result.single()['deleted'] == 0:
                    break
        logger.info("✓ 数据库已清空")
    
    def import_scene_graph(self, scene_data: Dict):
        nodes = scene_data.get('nodes') or scene_data.get('objects', [])
        edges = scene_data.get('edges') or scene_data.get('relationships', [])
        logger.info(f"导入场景图: {len(nodes)} 节点, {len(edges)} 边")
        
        with self.session() as session:
            batch_props = [{
                'unique_id': n['unique_id'],
                'type': n.get('type', 'unknown'),
                'status': n.get('status', 'unknown'),
                'category': n.get('category', '')
            } for n in nodes]
            session.run("UNWIND $batch as props CREATE (obj:Object) SET obj = props", batch=batch_props)
            try:
                session.run("CREATE CONSTRAINT object_unique_id IF NOT EXISTS FOR (obj:Object) REQUIRE obj.unique_id IS UNIQUE")
            except:
                pass
        
        with self.session() as session:
            batch_rels = []
            for edge in edges:
                props = {}
                # 1. 提取 distance
                if 'metrics' in edge:
                    m = edge['metrics']
                    if 'distance' in m:
                        props['distance'] = m['distance']
                    if 'angle' in m:
                        props['angle'] = m['angle']
                
                # 2. 提取方向信息 (使用 predicates)
                if 'predicates' in edge and isinstance(edge['predicates'], list):
                    props['angle_matches_ego'] = edge['predicates']
                elif 'direction_8' in edge:
                    # Fallback: 使用 direction_8
                    props['angle_matches_ego'] = [edge['direction_8']]
                elif 'direction_4' in edge:
                    # Fallback: 使用 direction_4
                    props['angle_matches_ego'] = [edge['direction_4']]
                
                batch_rels.append({'source': edge['source'], 'target': edge['target'], 'props': props})
            session.run("""
                UNWIND $batch as item
                MATCH (a:Object {unique_id: item.source})
                MATCH (b:Object {unique_id: item.target})
                CREATE (a)-[r:RELATES_TO]->(b)
                SET r = item.props
            """, batch=batch_rels)
        logger.info("✓ 场景图导入完成")
    
    def get_scene_totals(self) -> Dict[str, int]:
        """计算场景图的总数（分母）"""
        # 1. 节点总数
        r = self.execute_query("MATCH (n:Object) RETURN count(n) as c")
        total_nodes = r['data'][0]['c'] if r['success'] else 0
        
        # 2. 关系边总数
        r = self.execute_query("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as c")
        total_rel_edges = r['data'][0]['c'] if r['success'] else 0
        
        # 3. 属性边总数（只统计 status，type/category 是筛选条件）
        r = self.execute_query("""
            MATCH (n:Object)
            RETURN sum(CASE WHEN n.status IS NOT NULL AND n.status <> '' AND n.status <> 'unknown' THEN 1 ELSE 0 END) as c
        """)
        total_prop_edges = r['data'][0]['c'] if r['success'] else 0
        
        # 4. 二跳路径总数（简化版：子图中所有可能的二连边组合）
        # 4a. Rel -> Prop: 每条关系边的终点如果有 status，就形成一个二跳
        r = self.execute_query("""
            MATCH (a)-[:RELATES_TO]->(b)
            RETURN sum(CASE WHEN b.status IS NOT NULL AND b.status <> '' AND b.status <> 'unknown' THEN 1 ELSE 0 END) as c
        """)
        rel_prop_count = r['data'][0]['c'] if r['success'] else 0
        
        # 4b. Rel -> Rel: 所有能拓扑连通的边对（顺序、分叉、汇聚）
        # 统计方法：分别统计三种连通模式，然后求和
        
        # 顺序连通: (a)-[]->(b)-[]->(c)
        r = self.execute_query("""
            MATCH (a)-[:RELATES_TO]->(b)-[:RELATES_TO]->(c)
            WHERE a <> c
            RETURN count(*) as c
        """)
        sequential = r['data'][0]['c'] if r['success'] else 0
        
        # 分叉连通: (b)<-[]-(a)-[]->(c) where b < c (去重)
        r = self.execute_query("""
            MATCH (a)-[:RELATES_TO]->(b), (a)-[:RELATES_TO]->(c)
            WHERE id(b) < id(c)
            RETURN count(*) as c
        """)
        fork = r['data'][0]['c'] if r['success'] else 0
        
        # 汇聚连通: (a)-[]->(c)<-[]-(b) where a < b (去重)
        r = self.execute_query("""
            MATCH (a)-[:RELATES_TO]->(c), (b)-[:RELATES_TO]->(c)
            WHERE id(a) < id(b)
            RETURN count(*) as c
        """)
        converge = r['data'][0]['c'] if r['success'] else 0
        
        rel_rel_count = sequential + fork + converge
        
        total_2hop = rel_prop_count + rel_rel_count
        
        return {
            'nodes': total_nodes,
            'relation_edges': total_rel_edges,
            'property_edges': total_prop_edges,
            'total_edges': total_rel_edges + total_prop_edges,
            '2hop_paths': total_2hop
        }


# ============ LLM Cypher生成器 ============
class LLMCypherGenerator:
    """LLM Cypher生成器 - Ego Frame + angle_matches_ego"""
    
    SYSTEM_PROMPT = """你是Neo4j Cypher查询专家。

【Schema】
- 节点: Object (unique_id, type, status, category)
- 关系: RELATES_TO (source→target)
- 方向属性: angle_matches_ego (列表, 如['back', 'back-right'])

【方位规则 - Ego Frame】
所有方位以ego车为参考。查询方位用: 'DIR' IN r.angle_matches_ego
8方位: front, front-left, left, back-left, back, back-right, right, front-right
"X to the DIR of Y" → MATCH (Y)-[r:RELATES_TO]->(X) WHERE 'DIR' IN r.angle_matches_ego

【类型规则】
- trailer: category CONTAINS 'trailer'
- truck: type='truck' AND NOT category CONTAINS 'trailer'
- motorcycle: type='motorcycle' OR category CONTAINS 'motorcycle'
- bicycle: type='bicycle'
- car: type='car'
- pedestrian: type='pedestrian'
- ego/me: unique_id='ego'
- thing/object: type<>'barrier'

【status值】
- stopped, moving (车辆)
- with_rider, without_rider (自行车/摩托车)
- standing, sitting (行人)

【重要语义映射】
- "with rider thing" = status='with_rider' AND type<>'barrier'
- "without rider thing" = status='without_rider' AND type<>'barrier'
- "stopped thing" = status='stopped' AND type<>'barrier'
- "another X" = 不需要排除已有的，直接查询所有符合条件的X

【否定语义 - 极其重要】
- "not standing" = status <> 'standing' (不是 status='sitting'!)
- "not stopped" = status <> 'stopped'
- "not moving" = status <> 'moving'
- 否定语义用 <> 而不是瑨测另一个值

【查询模式示例】

1. 存在性检查 "Are any X visible?":
   MATCH (n:Object) WHERE n.type='X' RETURN COUNT(n) > 0 AS result

1b. "Are any with rider things visible?":
   MATCH (n:Object) WHERE n.status='with_rider' AND n.type<>'barrier'
   RETURN COUNT(n) > 0 AS result

2. 属性查询 "What is the status of X?":
   MATCH (n:Object) WHERE n.type='X' RETURN n.status LIMIT 1

3. 方向查询 "X to the back of Y":
   MATCH (y:Object)-[r:RELATES_TO]->(x:Object)
   WHERE y.type='Y' AND x.type='X' AND 'back' IN r.angle_matches_ego
   RETURN x LIMIT 1

4. 属性比较 "Does X have the same status as Y?":
   MATCH (x:Object), (y:Object)
   WHERE x.type='X' AND y.type='Y'
   RETURN x.status = y.status AS result LIMIT 1

5. 复杂比较 "same status as the Y that is to the DIR of Z":
   MATCH (z:Object)-[r:RELATES_TO]->(y:Object)
   WHERE z.type='Z' AND y.type='Y' AND 'DIR' IN r.angle_matches_ego
   WITH y.status AS target_status LIMIT 1
   MATCH (x:Object) WHERE x.type='X' AND x.status = target_status
   RETURN COUNT(x) > 0 AS result

6. "another X of same status as Y" / "Is there a X of same status as Y?":
   MATCH (y:Object) WHERE y.type='Y'
   WITH y.status AS target_status LIMIT 1
   MATCH (x:Object) WHERE x.type='X' AND x.status = target_status
   RETURN COUNT(x) > 0 AS result
   
   注意: "another" 不需要特殊处理，直接查找所有同状态的对象即可

7. 复合方向 "X that is both to DIR1 of A and to DIR2 of B":
   MATCH (a:Object)-[r1:RELATES_TO]->(x:Object),
         (b:Object)-[r2:RELATES_TO]->(x)
   WHERE a.status='stopped' AND a.category CONTAINS 'trailer'
     AND 'back-right' IN r1.angle_matches_ego
     AND b.status='stopped' AND b.type='truck'
     AND 'back' IN r2.angle_matches_ego
     AND x.type<>'barrier'
   RETURN x.type AS result LIMIT 1

8. 极复杂比较 "Is status of X1(to DIR1 of Y1) same as X2(to DIR2 of Y2)?":
   // 先找第一个对象
   MATCH (y1:Object)-[r1:RELATES_TO]->(x1:Object)
   WHERE y1.status<>'standing' AND y1.type='pedestrian'
     AND x1.type='bus' AND 'back-right' IN r1.angle_matches_ego
   WITH x1.status AS status1 LIMIT 1
   // 再找第二个对象比较
   MATCH (y2:Object)-[r2:RELATES_TO]->(x2:Object)
   WHERE y2.status='stopped' AND y2.category CONTAINS 'trailer'
     AND x2.type='bus' AND 'front' IN r2.angle_matches_ego
   RETURN status1 = x2.status AS result LIMIT 1

9. COUNT问题 "What number of X in same status as Y to DIR of Z?":
   MATCH (z:Object)-[r:RELATES_TO]->(y:Object)
   WHERE z.type='truck' AND y.type='pedestrian' AND 'back-right' IN r.angle_matches_ego
   WITH y.status AS target_status LIMIT 1
   MATCH (x:Object) WHERE x.type<>'barrier' AND x.status = target_status
   RETURN COUNT(x) AS result

10. 存在性+方向 "Are there any X to DIR of Y?":
    MATCH (y:Object)-[r:RELATES_TO]->(x:Object)
    WHERE y.status='stopped' AND y.category CONTAINS 'trailer'
      AND x.status='with_rider' AND x.type='bicycle'
      AND 'front-left' IN r.angle_matches_ego
    RETURN COUNT(x) > 0 AS result

11. 嵌套方向+比较 "same status as X to DIR of (Y with status)?":
    // "the truck to the back right of the with rider bicycle"
    MATCH (y:Object)-[r:RELATES_TO]->(x:Object)
    WHERE y.status='with_rider' AND y.type='bicycle'
      AND x.type='truck' AND NOT x.category CONTAINS 'trailer'
      AND 'back-right' IN r.angle_matches_ego
    WITH x.status AS target_status LIMIT 1
    // 然后用target_status进行比较...

12. "to the DIR of me/ego":
    MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(x:Object)
    WHERE 'back-right' IN r.angle_matches_ego AND x.status='moving'
    RETURN x LIMIT 1

13. 复合条件 "X to DIR1 of me AND to DIR2 of Y":
    MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(x:Object),
          (y:Object)-[r2:RELATES_TO]->(x)
    WHERE 'back-right' IN r1.angle_matches_ego
      AND 'back-right' IN r2.angle_matches_ego
      AND y.type='bus' AND x.status='moving' AND x.type<>'barrier'
    RETURN x.type AS result LIMIT 1

14. "There is a X; is its status same as Y to DIR of Z?" (X无方向限定):
    // "有一个motorcycle，它的status和pedestrian to back-right of with rider thing相同吗"
    // 先找第一个对象的status
    MATCH (x:Object)
    WHERE x.type='motorcycle' OR x.category CONTAINS 'motorcycle'
    WITH x.status AS status1 LIMIT 1
    // 再找第二个对象(Y to DIR of Z)的status
    MATCH (z:Object)-[r:RELATES_TO]->(y:Object)
    WHERE z.status='with_rider' AND z.type<>'barrier'
      AND y.type='pedestrian' AND 'back-right' IN r.angle_matches_ego
    RETURN status1 = y.status AS result LIMIT 1

15. "Is trailer same status as truck to DIR of with rider bicycle?":
    // trailer无方向限定，truck有方向限定
    MATCH (trailer:Object)
    WHERE trailer.category CONTAINS 'trailer'
    WITH trailer.status AS status1 LIMIT 1
    MATCH (bike:Object)-[r:RELATES_TO]->(truck:Object)
    WHERE bike.status='with_rider' AND bike.type='bicycle'
      AND truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
      AND 'back-right' IN r.angle_matches_ego
    RETURN status1 = truck.status AS result LIMIT 1

16. "What number of other things same status as trailer?" (trailer无方向):
    MATCH (trailer:Object)
    WHERE trailer.category CONTAINS 'trailer'
    WITH trailer.status AS target_status LIMIT 1
    MATCH (x:Object)
    WHERE x.type<>'barrier' AND x.status = target_status
      AND NOT x.category CONTAINS 'trailer'
    RETURN COUNT(x) AS result

17. "Is there another X same status as X to DIR of (Y with status)?":
    // "是否有另一个truck和truck to front-left of with rider thing同状态"
    MATCH (y:Object)-[r:RELATES_TO]->(x:Object)
    WHERE y.status='with_rider' AND y.type<>'barrier'
      AND x.type='truck' AND NOT x.category CONTAINS 'trailer'
      AND 'front-left' IN r.angle_matches_ego
    WITH x.status AS target_status LIMIT 1
    MATCH (other:Object)
    WHERE other.type='truck' AND NOT other.category CONTAINS 'trailer'
      AND other.status = target_status
    RETURN COUNT(other) > 0 AS result

18. 极复杂双重比较 "Is X1(to DIR1 of Y1) same status as X2(to DIR2 of Y2)?" (两个都有方向):
    // "bus to back-right of not standing pedestrian" vs "truck to back-right of with rider thing"
    MATCH (y1:Object)-[r1:RELATES_TO]->(x1:Object)
    WHERE y1.type='pedestrian' AND y1.status<>'standing'
      AND x1.type='bus' AND 'back-right' IN r1.angle_matches_ego
    WITH x1.status AS status1 LIMIT 1
    MATCH (y2:Object)-[r2:RELATES_TO]->(x2:Object)
    WHERE y2.status='with_rider' AND y2.type<>'barrier'
      AND x2.type='truck' AND NOT x2.category CONTAINS 'trailer'
      AND 'back-right' IN r2.angle_matches_ego
    RETURN status1 = x2.status AS result LIMIT 1

19. "Does trailer have same status as truck to DIR of bicycle?" (bicycle无status限定):
    MATCH (trailer:Object)
    WHERE trailer.category CONTAINS 'trailer'
    WITH trailer.status AS status1 LIMIT 1
    MATCH (bike:Object)-[r:RELATES_TO]->(truck:Object)
    WHERE bike.type='bicycle'
      AND truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
      AND 'back-right' IN r.angle_matches_ego
    RETURN status1 = truck.status AS result LIMIT 1

20. "Are there any other things that/in same status as X?" (存在性+同状态):
    MATCH (x:Object)
    WHERE x.type='truck' AND NOT x.category CONTAINS 'trailer'
    WITH x.status AS target_status, x.unique_id AS exclude_id LIMIT 1
    MATCH (other:Object)
    WHERE other.type<>'barrier' AND other.status = target_status
      AND other.unique_id <> exclude_id
    RETURN COUNT(other) > 0 AS result

【重要规则】
- "the X" / "a X" (单数) → 必须加 LIMIT 1
- "Are any..." / "Is there..." → 用 COUNT(...) > 0
- 属性比较用 WITH 传递属性值

【禁止】
- 禁止使用 r.direction / r.predicates
- 只能用 r.angle_matches_ego
- 禁止使用 EXISTS{} 子查询

【输出】只输出一个Cypher代码块:
```cypher
<查询>
```"""
    
    def __init__(self):
        import httpx
        from openai import OpenAI
        
        api_key = os.getenv("VQA_API_KEY", "sk-ecd91655d033446b9ae8ea390e65d923")
        api_base = os.getenv("VQA_API_BASE_URL", "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1")
        self.model = os.getenv("VQA_MODEL_NAME", "deepseek-r1")
        verify = os.getenv('VQA_VERIFY_SSL', 'false').lower() in ('true', '1')
        
        http_client = httpx.Client(verify=verify) if not verify else None
        self.client = OpenAI(api_key=api_key, base_url=api_base, http_client=http_client)
    
    def generate_cypher(self, question: str) -> Optional[str]:
        prompt = f"Question: {question}\n\n将问题转为Cypher。"
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2048
            )
            content = resp.choices[0].message.content
            return self._extract_cypher(content)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return None
    
    def _extract_cypher(self, content: str) -> Optional[str]:
        if not content:
            return None
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        m = re.search(r'```cypher\s*(.*?)```', content, re.DOTALL | re.I)
        if m:
            return m.group(1).strip().rstrip(';')
        m = re.search(r'```\s*(.*?)```', content, re.DOTALL)
        if m and ('MATCH' in m.group(1).upper() or 'RETURN' in m.group(1).upper()):
            return m.group(1).strip().rstrip(';')
        return None


# ============ 极严苛版 覆盖分析器 ============
class CoverageAnalyzer:
    """
    分析Cypher查询真实覆盖的图元素 (逻辑自适应版)
    
    特性：
    1. 镜像 LIMIT：严格尊重 LLM 生成的 LIMIT 约束，不强行修改
    2. 逻辑二跳：支持 顺序路径(->->) 和 分叉路径(<- ->) 和 汇聚路径(-> <-)
    3. 无静态兆底：动态执行失败即视为 0 覆盖，倒逼 Cypher 质量
    """
    
    def __init__(self, neo4j: Neo4jClient, valid_nodes: Set[str] = None):
        self.neo4j = neo4j
        self.valid_nodes = valid_nodes
    
    def analyze(self, cypher: str) -> Tuple[Set[str], Set[Tuple], Set[Tuple]]:
        """返回: (覆盖的节点unique_id集合, 覆盖的边集合, 覆盖的两跳路径集合)"""
        # 关键修复：处理 WITH 子句
        # WITH 会消耗变量，所以需要分阶段收集覆盖
        
        nodes = set()
        rel_edges = set()
        all_connections = []
        
        # 分阶段执行：在每个 WITH 之前收集覆盖
        stages = self._split_by_with(cypher)
        
        for stage_idx, stage in enumerate(stages):
            injected, node_vars, rel_vars = self._inject_return_statement(stage)
            stage_nodes, stage_edges, stage_conns = self._execute_and_extract(injected, node_vars, rel_vars)
            
            nodes.update(stage_nodes)
            rel_edges.update(stage_edges)
            all_connections.extend(stage_conns)
        
        # 过滤无效节点
        if self.valid_nodes:
            nodes = nodes & self.valid_nodes
            rel_edges = {e for e in rel_edges if e[0] in self.valid_nodes and e[1] in self.valid_nodes}
        
        # 提取属性边
        prop_edges = self._extract_property_edges(cypher, nodes)
        
        # 合并边
        all_edges = rel_edges | prop_edges
        
        # 计算二跳路径
        paths_2hop = self._find_contextual_2hop(rel_edges, prop_edges, all_connections)
        
        return nodes, all_edges, paths_2hop
    
    def _split_by_with(self, cypher: str) -> List[str]:
        """
        按 WITH 子句分割查询，返回多个阶段
        每个阶段包含 MATCH ... [WHERE ...] [WITH ...]
        """
        # 查找所有 WITH 的位置
        with_positions = []
        for m in re.finditer(r'\bWITH\b', cypher, re.I):
            with_positions.append(m.start())
        
        if not with_positions:
            # 没有 WITH，返回原始查询
            return [cypher]
        
        stages = []
        start = 0
        
        for with_pos in with_positions:
            # 找到 WITH 语句的结束位置（下一个 MATCH 或 RETURN）
            rest = cypher[with_pos:]
            next_clause = re.search(r'\b(MATCH|RETURN)\b', rest[5:], re.I)  # 跳过 WITH 本身
            
            if next_clause:
                # WITH 语句到下一个子句之前
                with_end = with_pos + 5 + next_clause.start()
                stage = cypher[start:with_end].strip()
            else:
                # 最后一个 WITH，到查询结束
                stage = cypher[start:].strip()
            
            if stage:
                stages.append(stage)
            start = with_end if next_clause else len(cypher)
        
        # 处理最后一个阶段（如果有）
        if start < len(cypher):
            final_stage = cypher[start:].strip()
            if final_stage:
                stages.append(final_stage)
        
        return stages if stages else [cypher]
    
    def _inject_return_statement(self, cypher: str) -> Tuple[str, List[str], List[str]]:
        """
        为单个阶段注入RETURN语句
        阶段可能以 WITH 结尾，需要在 WITH 之前注入 RETURN
        返回: (新Cypher, 节点变量, 关系变量)
        """
        # 1. 提取节点和关系变量
        node_vars = list(set(m.group(1) for m in re.finditer(r'\((\w+)(?::\w+)?(?:\s*\{[^}]*\})?\)', cypher)))
        rel_vars = list(set(m.group(1) for m in re.finditer(r'\[(\w+)(?::[\w_]+)?(?:\s*\{[^}]*\})?\]', cypher)))
        node_vars = [v for v in node_vars if v not in rel_vars]
        
        if not node_vars and not rel_vars:
            return cypher, [], []
        
        # 2. 构造 RETURN 内容
        return_items = [f"{v}.unique_id AS {v}_id" for v in node_vars]
        return_items += [f"startNode({r}).unique_id AS {r}_src, endNode({r}).unique_id AS {r}_tgt" for r in rel_vars]
        new_return_content = ', '.join(return_items)
        
        # 3. 判断是否有 WITH
        has_with = bool(re.search(r'\bWITH\b', cypher, re.I))
        
        if has_with:
            # 如果有 WITH，在 WITH 之前注入 RETURN
            # 找到 WITH 之前的最后一个子句（WHERE 或 MATCH）
            with_match = re.search(r'\bWITH\b', cypher, re.I)
            if with_match:
                before_with = cypher[:with_match.start()].rstrip()
                # 在 WITH 之前注入 RETURN
                new_cypher = before_with + f" RETURN {new_return_content}"
        else:
            # 如果没有 WITH，替换或添加 RETURN
            pattern = r'RETURN\s+.*?(?=\s+LIMIT|\s+ORDER\s+BY|$)'
            if re.search(pattern, cypher, flags=re.I | re.DOTALL):
                new_cypher = re.sub(pattern, f'RETURN {new_return_content}', cypher, count=1, flags=re.I | re.DOTALL)
            else:
                new_cypher = cypher + f" RETURN {new_return_content}"
        
        return new_cypher, node_vars, rel_vars
    
    
    def _execute_and_extract(self, analysis_cypher: str, 
                             node_vars: List[str], rel_vars: List[str]) -> Tuple[Set[str], Set[Tuple], List[List[Tuple]]]:
        """
        执行查询。如果失败，直接返回空 (Hard Fail)。
        无静态兆底，倒逼 LLM 生成高质量 Cypher。
        """
        nodes = set()
        edges = set()
        connections = []  # 记录共现关系 (用于算 L2)
        
        result = self.neo4j.execute_query(analysis_cypher)
        
        if result['success'] and result['data']:
            for row in result['data']:
                row_edges = []
                # 提取节点 (_id 结尾)
                for k, v in row.items():
                    if k.endswith('_id') and v:
                        nodes.add(v)
                    elif k.endswith('_src'):
                        rel = k[:-4]
                        tgt_k = f"{rel}_tgt"
                        if tgt_k in row and row[k] and row[tgt_k]:
                            src, tgt = row[k], row[tgt_k]
                            edge = (src, tgt)
                            edges.add(edge)
                            row_edges.append(edge)
                            nodes.add(src)
                            nodes.add(tgt)
                
                # 记录这一行里的边连接情况 (用于算 L2)
                if row_edges:
                    connections.append(row_edges)
        
        # 彻底移除静态兆底：执行失败或返回空都直接返回空集合
        
        return nodes, edges, connections
    
    def _extract_property_edges(self, cypher: str, nodes: Set[str]) -> Set[Tuple]:
        """批量提取属性边 - 只统计status，type/category是筛选条件不算边"""
        props = set()
        # 只统计 status 作为属性边，type/category 是静态标签用于筛选，不算“被测试的边”
        for m in re.finditer(r'\w+\.(status)', cypher, re.I):
            props.add(m.group(1).lower())
        
        edges = set()
        if not nodes or not props:
            return edges
        
        query = "MATCH (n:Object) WHERE n.unique_id IN $ids RETURN n.unique_id as id, n.type as t, n.status as s, n.category as c"
        res = self.neo4j.execute_query(query, parameters={'ids': list(nodes)})
        
        if res['success']:
            key_map = {'type': 't', 'status': 's', 'category': 'c'}
            for row in res['data']:
                nid = row['id']
                for p in props:
                    val = row.get(key_map.get(p))
                    if val and val != '' and val != 'unknown':
                        edges.add((nid, f"{p}:{val}"))
        return edges
    
    def _find_contextual_2hop(self, rel_edges: Set[Tuple], prop_edges: Set[Tuple], 
                               connections: List[List[Tuple]]) -> Set[Tuple]:
        """
        计算二跳路径 - 简化版：子图中所有二连边组合
        
        核心原则：
        1. 关系->属性: 统计所有关系边的目标节点的属性边
        2. 关系->关系: 统计子图中所有能连通的二连边（顺序、分叉、汇聚）
        
        不再进行复杂的语法分析和意图判断，直接基于查询返回的子图结构计算。
        """
        paths = set()
        
        # ========== 类型1：关系 -> 属性 ==========
        # 关系边的终点有属性边，形成 (src, tgt, prop)
        for r_edge in rel_edges:
            src, tgt = r_edge
            for p_edge in prop_edges:
                if p_edge[0] == tgt:
                    paths.add((src, tgt, p_edge[1]))
        
        # ========== 类型2：关系 -> 关系 ==========
        # 在查询返回的子图中，找所有拓扑上能连通的边对
        # 遍历所有关系边的组合，检查是否有共享节点
        rel_edges_list = list(rel_edges)
        for i in range(len(rel_edges_list)):
            for j in range(i+1, len(rel_edges_list)):
                e1, e2 = rel_edges_list[i], rel_edges_list[j]
                
                # 情况A: 顺序连通 A->B->C (e1的终点是e2的起点)
                if e1[1] == e2[0]:
                    paths.add((e1[0], e1[1], e2[1]))
                # 反向顺序 C->B->A (e2的终点是e1的起点)
                elif e2[1] == e1[0]:
                    paths.add((e2[0], e2[1], e1[1]))
                
                # 情况B: 分叉连通 B<-A->C (共享起点，标准化存储)
                elif e1[0] == e2[0]:
                    leaf1, leaf2 = sorted([e1[1], e2[1]])
                    paths.add((leaf1, e1[0], leaf2))
                
                # 情况C: 汇聚连通 A->C<-B (共享终点，标准化存储)
                elif e1[1] == e2[1]:
                    root1, root2 = sorted([e1[0], e2[0]])
                    paths.add((root1, e1[1], root2))
        
        return paths


# ============ 主Pipeline ============
class CoveragePipeline:
    def __init__(self, scene_graph_path: str, questions_path: str, output_dir: str):
        self.sg_path = Path(scene_graph_path)
        self.questions_path = Path(questions_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.sg_path, 'r', encoding='utf-8') as f:
            self.sg_data = json.load(f)
        self.scene_name = self.sg_data.get('scene_name', 'unknown')
        self.frame_idx = self.sg_data.get('frame_idx', 0)
        
        with open(self.questions_path, 'r', encoding='utf-8') as f:
            self.questions_data = json.load(f)
        
        self.neo4j = Neo4jClient()
        self.llm = LLMCypherGenerator()
        self.analyzer = None
        self.stats = CoverageStats()
        self.results = []
        self.detail_log = []
    
    def run(self) -> Dict:
        if not self.neo4j.connect():
            logger.error("无法连接Neo4j")
            return {}
        
        try:
            self.neo4j.clear_database()
            self.neo4j.import_scene_graph(self.sg_data)
            
            totals = self.neo4j.get_scene_totals()
            self.stats.total_nodes = totals['nodes']
            self.stats.total_edges = totals['total_edges']
            self.stats.total_2hop_paths = totals['2hop_paths']
            
            # 提取场景图中的有效节点ID
            valid_nodes = {n['unique_id'] for n in self.sg_data.get('nodes', [])}
            self.analyzer = CoverageAnalyzer(self.neo4j, valid_nodes)
            questions = self._extract_questions()
            self.stats.total_questions = len(questions)
            
            logger.info(f"场景: {self.scene_name} 帧{self.frame_idx}")
            logger.info(f"节点: {totals['nodes']}, 边: {totals['total_edges']}, 两跳: {totals['2hop_paths']}")
            logger.info(f"题目数: {len(questions)}")
            logger.info("-" * 50)
            
            for i, q in enumerate(questions, 1):
                question = q['question']
                logger.info(f"[{i}/{len(questions)}] {question}")
                
                log_entry = {'idx': i, 'question': question}
                
                cypher = self.llm.generate_cypher(question)
                if not cypher:
                    logger.warning("  ❌ Cypher生成失败")
                    self.stats.failed_questions += 1
                    log_entry['status'] = 'FAILED'
                    log_entry['error'] = 'Cypher生成失败'
                    self.detail_log.append(log_entry)
                    self.results.append({'question': question, 'cypher': None, 'error': 'Cypher生成失败'})
                    continue
                
                log_entry['cypher'] = cypher
                logger.info(f"  Cypher:\n{cypher}")
                
                try:
                    nodes, edges, paths = self.analyzer.analyze(cypher)
                    self.stats.covered_nodes.update(nodes)
                    self.stats.covered_edges.update(edges)
                    self.stats.covered_2hop_paths.update(paths)
                    self.stats.analyzed_questions += 1
                    
                    log_entry['status'] = 'OK'
                    log_entry['nodes'] = len(nodes)
                    log_entry['edges'] = len(edges)
                    log_entry['paths_2hop'] = len(paths)
                    log_entry['node_list'] = sorted(nodes)
                    
                    logger.info(f"  → 节点: {len(nodes)}, 边: {len(edges)}, 两跳: {len(paths)}")
                    self.results.append({
                        'question': question,
                        'cypher': cypher,
                        'covered_nodes': list(nodes),
                        'covered_edges': [list(e) for e in edges],
                        'covered_2hop_paths': [list(p) for p in paths]
                    })
                except Exception as e:
                    logger.warning(f"  ❌ 分析失败: {e}")
                    self.stats.failed_questions += 1
                    log_entry['status'] = 'ERROR'
                    log_entry['error'] = str(e)
                    self.results.append({'question': question, 'cypher': cypher, 'error': str(e)})
                
                self.detail_log.append(log_entry)
            
            self._print_summary()
            self._save_detail_log()
            return self._save_results()
        finally:
            self.neo4j.close()
    
    def _extract_questions(self) -> List[Dict]:
        if isinstance(self.questions_data, dict):
            # 新格式: {'scene_name': 'xxx', 'frame_idx': N, 'results': [...]}
            if 'results' in self.questions_data:
                results = self.questions_data['results']
                # 检查 scene/frame 匹配
                if self.questions_data.get('scene_name') == self.scene_name and \
                   self.questions_data.get('frame_idx') == self.frame_idx:
                    return [{'question': r['question']} for r in results if 'question' in r]
                else:
                    logger.warning(f"场景不匹配: 题目文件={self.questions_data.get('scene_name')}_frame{self.questions_data.get('frame_idx')}, 场景图={self.scene_name}_frame{self.frame_idx}")
                    return []
            
            if any(k.startswith('Q') for k in self.questions_data.keys()):
                return [
                    {'id': qid, 'question': qd['question']}
                    for qid, qd in self.questions_data.items()
                    if isinstance(qd, dict) and 
                       qd.get('metadata', {}).get('scene_name') == self.scene_name and
                       qd.get('metadata', {}).get('frame_index') == self.frame_idx
                ]
            if 'questions' in self.questions_data:
                return self.questions_data['questions']
            if 'qa_pairs' in self.questions_data:
                return [{'question': q['question']} for q in self.questions_data['qa_pairs']]
        if isinstance(self.questions_data, list):
            return [{'question': q} if isinstance(q, str) else q for q in self.questions_data]
        raise ValueError("无法解析题目文件")
    
    def _print_summary(self):
        rates = self.stats.get_rates()
        logger.info("\n" + "=" * 60)
        logger.info("  覆盖率统计")
        logger.info("=" * 60)
        logger.info(f"题目: {self.stats.total_questions}, 成功: {self.stats.analyzed_questions}, 失败: {self.stats.failed_questions}")
        logger.info(f"L0 (节点): {len(self.stats.covered_nodes)}/{self.stats.total_nodes} = {rates['L0']:.2%}")
        logger.info(f"L1 (边):   {len(self.stats.covered_edges)}/{self.stats.total_edges} = {rates['L1']:.2%}")
        logger.info(f"L2 (两跳): {len(self.stats.covered_2hop_paths)}/{self.stats.total_2hop_paths} = {rates['L2']:.2%}")
        logger.info("=" * 60)
    
    def _save_detail_log(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.output_dir / f"coverage_detail_{self.scene_name}_frame{self.frame_idx}_{ts}.txt"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"覆盖率评估详细日志\n")
            f.write(f"场景: {self.scene_name} 帧{self.frame_idx}\n")
            f.write(f"时间: {ts}\n")
            f.write(f"节点总数: {self.stats.total_nodes}, 边总数: {self.stats.total_edges}\n")
            f.write("=" * 80 + "\n\n")
            
            for entry in self.detail_log:
                f.write(f"[{entry['idx']}] {entry['question']}\n")
                f.write("-" * 80 + "\n")
                
                if entry['status'] == 'FAILED':
                    f.write(f"状态: ❌ {entry.get('error', 'Cypher生成失败')}\n")
                elif entry['status'] == 'ERROR':
                    f.write(f"状态: ⚠️ 分析错误: {entry.get('error')}\n")
                    f.write(f"Cypher:\n{entry.get('cypher', 'N/A')}\n")
                else:
                    f.write(f"状态: ✓ 节点={entry['nodes']}, 边={entry['edges']}, 两跳={entry['paths_2hop']}\n")
                    f.write(f"覆盖节点: {entry.get('node_list', [])}\n")
                    f.write(f"Cypher:\n{entry.get('cypher', 'N/A')}\n")
                
                f.write("\n")
            
            rates = self.stats.get_rates()
            f.write("=" * 80 + "\n")
            f.write("汇总\n")
            f.write(f"题目: {self.stats.total_questions}, 成功: {self.stats.analyzed_questions}, 失败: {self.stats.failed_questions}\n")
            f.write(f"L0 (节点): {len(self.stats.covered_nodes)}/{self.stats.total_nodes} = {rates['L0']:.2%}\n")
            f.write(f"L1 (边):   {len(self.stats.covered_edges)}/{self.stats.total_edges} = {rates['L1']:.2%}\n")
            f.write(f"L2 (两跳): {len(self.stats.covered_2hop_paths)}/{self.stats.total_2hop_paths} = {rates['L2']:.2%}\n")
            f.write(f"\n覆盖的节点列表:\n{sorted(self.stats.covered_nodes)}\n")
        
        logger.info(f"详细日志已保存: {log_file}")
    
    def _save_results(self) -> Dict:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rates = self.stats.get_rates()
        data = {
            'timestamp': ts,
            'scene': {'name': self.scene_name, 'frame_idx': self.frame_idx},
            'totals': {'nodes': self.stats.total_nodes, 'edges': self.stats.total_edges, '2hop': self.stats.total_2hop_paths},
            'questions': {'total': self.stats.total_questions, 'analyzed': self.stats.analyzed_questions, 'failed': self.stats.failed_questions},
            'coverage': {
                'L0': {'covered': len(self.stats.covered_nodes), 'total': self.stats.total_nodes, 'rate': rates['L0'], 'nodes': sorted(self.stats.covered_nodes)},
                'L1': {'covered': len(self.stats.covered_edges), 'total': self.stats.total_edges, 'rate': rates['L1']},
                'L2': {'covered': len(self.stats.covered_2hop_paths), 'total': self.stats.total_2hop_paths, 'rate': rates['L2']}
            },
            'details': self.results
        }
        out_file = self.output_dir / f"coverage_{self.scene_name}_frame{self.frame_idx}_{ts}.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存: {out_file}")
        return data


def main():
    import argparse
    parser = argparse.ArgumentParser(description='覆盖率评估Pipeline')
    parser.add_argument('--scene-graph', '-s', required=True)
    parser.add_argument('--questions', '-q', required=True)
    parser.add_argument('--output', '-o', default='output/coverage')
    args = parser.parse_args()
    
    CoveragePipeline(args.scene_graph, args.questions, args.output).run()


if __name__ == "__main__":
    main()
