"""
VQA Pipeline 配置文件 - 基于业界最佳实践优化
"""

# ============ API配置 ============
API_BASE_URL = "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1"
API_KEY = "sk-ecd91655d033446b9ae8ea390e65d923"
APP_ID = "61cb0d25ba9049d284ff68f9941481be"
MODEL_NAME = "deepseek-r1"

REQUEST_TIMEOUT = 120
MAX_RETRIES = 3

# ============ Neo4j配置 ============
NEO4J_URI = "bolt://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

# ============ 场景图Schema ============
SCENE_GRAPH_SCHEMA = """Neo4j场景图Schema:

节点 (Label: Object):
- unique_id: 对象唯一标识 (如'ego', 'car1', 'pedestrian1')
- type: 对象类型 (ego/car/truck/bus/bicycle/pedestrian/barrier/motorcycle/trailer)
- category: NuScenes类别 (如'vehicle.car', 'vehicle.trailer', 'vehicle.motorcycle')
- status: 对象状态 (stopped/moving/with_rider/without_rider/parked/standing/unknown)
- attributes: NuScenes原始属性标签列表

⚠️ 重要约束:
- 不存在 translation/rotation/size/velocity 等属性，不要在Cypher中访问这些字段
- 速度/位置等信息已离散化到 status 属性和 RELATES_TO 关系中

关系 (Type: RELATES_TO):
- predicates: [方位, 距离级别]
  * predicates[0]: 8方位 'front'/'front-left'/'left'/'back-left'/'back'/'back-right'/'right'/'front-right'
  * predicates[1]: 距离级别 'near'(≤10m)/'mid'(10-25m)/'far'(>25m)
- direction_4: 4方位 'front'/'left'/'back'/'right' (±45°范围)
- direction_8: 8方位，同predicates[0] (±22.5°范围)
- distance: 精确距离(米)
- angle: 相对角度(度)

方位选择规则:
- 单一方位词(front/back/left/right) → 使用 r.direction_4
- 复合方位词(front-left/back-right等) → 使用 r.predicates[0]

特殊类型:
- trailer: WHERE n.category CONTAINS 'trailer'
- truck(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- motorcycle: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'

方位语义(参照物关系):
"X to DIRECTION of Y" → Y是参照物，X是目标
Cypher: MATCH (Y)-[r:RELATES_TO]->(X) WHERE r.DIRECTION_FIELD='DIRECTION'
"""

# ============ Cypher生成主Prompt ============
QUESTION_TO_CYPHER_PROMPT = """You are a Neo4j Cypher query expert. Generate executable Cypher queries from natural language questions.

{schema}

Question: {question}
Question Type: {question_type}
Previous Error (if retry): {prev_error}

🔧 CRITICAL RULES:

1. Object Types: ego, car, truck, bus, bicycle, pedestrian, barrier, motorcycle, trailer

2. Special Type Queries:
   - trailer: WHERE n.category CONTAINS 'trailer'
   - truck (exclude trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
   - motorcycle: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'

3. ⭐⭐⭐ STATUS ATTRIBUTE (EXTREMELY IMPORTANT):
   - status is a stored node property, NOT computed from velocity
   - Possible values: 'stopped', 'moving', 'with_rider', 'without_rider', 'parked', 'standing', 'unknown'
   
   Common Query Patterns:
   - "with rider thing" → WHERE n.status='with_rider'
   - "without rider thing" → WHERE n.status='without_rider'  
   - "stopped thing" → WHERE n.status='stopped'
   - "moving thing" → WHERE n.status='moving'
   - "What is the status of X?" → RETURN X.status
   - "What status is X?" → RETURN X.status
   
   ❌ NEVER use velocity/translation/rotation (they don't exist)
   ❌ NEVER use n.type to represent "same status"
   ✅ ALWAYS use n.status for state queries

4. Direction Semantics (CRITICAL):
   - "X to DIR of Y" → Y is reference, match: (Y)-[r]->(X)
   - 4-direction word → use r.direction_4
   - 8-direction word → use r.predicates[0]
   
   Example: "truck to the back of me"
   → MATCH (ego:Object {{unique_id:'ego'}})-[r]->(truck) WHERE r.direction_4='back'

5. "other things" semantics:
   - Refers to: [ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian]
   - Does NOT include: barrier

6. Uniqueness ("the X"):
   - "the X" implies unique or can be uniquely determined
   - "the trailer" → WHERE n.category CONTAINS 'trailer' LIMIT 1
   - "the stopped truck" → WHERE n.type='truck' AND n.status='stopped' LIMIT 1

7. ⚠️ WITH Variable Constraint Issue:
   - If you define WITH variables, MUST use them in subsequent WHERE clause
   - ❌ Wrong: WITH refStatus ... MATCH (o) WHERE o.type='car' RETURN count(o)
   - ✅ Right: WITH refStatus, refId ... WHERE o.status=refStatus AND o.unique_id<>refId

8. Structure Constraints:
   - Generate ONLY ONE query with ONE RETURN statement
   - RETURN must be at the end
   - No MATCH/RETURN after RETURN
   - Multi-hop: chain MATCH clauses, don't write multiple queries

🧭 COMMON PATTERNS:

Pattern A - Status Comparison (two spatially-defined objects):
MATCH (ref1:Object) WHERE <ref1_constraints>
MATCH (ref1)-[r1:RELATES_TO]->(obj1:Object) WHERE <obj1_constraints> AND <dir1>
WITH ref1, obj1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (ref2:Object) WHERE <ref2_constraints>  
MATCH (ref2)-[r2:RELATES_TO]->(obj2:Object) WHERE <obj2_constraints> AND <dir2>
WITH obj1, obj2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN obj1.status = obj2.status AS same_status

Pattern B - Same Status Count:
MATCH (ref:Object) WHERE <ref_constraints>
MATCH (ref)-[r1:RELATES_TO]->(ref_target:Object) WHERE <target_constraints> AND <dir>
WITH ref_target, r1 ORDER BY r1.distance ASC LIMIT 1
WITH ref_target.status AS refStatus, ref_target.unique_id AS refId

MATCH (other:Object)
WHERE other.type='<target_type>'
  AND other.status=refStatus    // ⚠️ MUST use refStatus
  AND other.unique_id<>refId     // ⚠️ MUST use refId
RETURN count(other) AS count

Pattern C - Multi-Anchor:
MATCH (ref1:Object) WHERE <ref1_constraints>
MATCH (ref2:Object) WHERE <ref2_constraints>
MATCH (ref1)-[r1:RELATES_TO]->(target:Object) WHERE <dir1>
MATCH (ref2)-[r2:RELATES_TO]->(target) WHERE <dir2>
WITH target, r1, r2 ORDER BY r1.distance+r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status

📝 EXAMPLE 1 - Status Query:
Question: "What is the status of the motorcycle?"
Cypher:
【CYPHER】
MATCH (m:Object) WHERE m.type='motorcycle' OR m.category CONTAINS 'motorcycle'
RETURN m.status LIMIT 1
【/CYPHER】

📝 EXAMPLE 2 - With/Without Rider:
Question: "What is the with rider thing?"
Cypher:
【CYPHER】
MATCH (n:Object) WHERE n.status='with_rider'
RETURN n.type LIMIT 1
【/CYPHER】

Question: "What is the without rider thing?"
Cypher:
【CYPHER】
MATCH (n:Object) WHERE n.status='without_rider'
RETURN n.type LIMIT 1
【/CYPHER】

📝 EXAMPLE 3 - Stopped Thing:
Question: "There is a stopped thing to the back of me; what is it?"
Cypher:
【CYPHER】
MATCH (ego:Object {{unique_id:'ego'}})-[r:RELATES_TO]->(obj:Object)
WHERE obj.status='stopped' AND r.direction_4='back'
WITH obj, r ORDER BY r.distance ASC LIMIT 1
RETURN obj.type
【/CYPHER】

📝 EXAMPLE 4 - Status Comparison:
Question: "Is the status of the bus to the back right of the not standing pedestrian the same as the bus to the front of the stopped trailer?"
Cypher:
【CYPHER】
MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object) WHERE bus1.type='bus' AND r1.predicates[0]='back-right'
WITH ped, bus1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object) WHERE bus2.type='bus' AND r2.direction_4='front'
WITH bus1, bus2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN bus1.status=bus2.status AS same_status
【/CYPHER】

📝 EXAMPLE 5 - Same Status Existence:
Question: "Is there another bicycle of the same status as the truck?"
Cypher:
【CYPHER】
MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
WITH truck.status AS truckStatus, truck.unique_id AS truckId LIMIT 1

MATCH (bicycle:Object)
WHERE bicycle.type='bicycle'
  AND bicycle.status=truckStatus
  AND bicycle.unique_id<>truckId
RETURN count(bicycle) > 0 AS exist
【/CYPHER】

🎯 OUTPUT FORMAT:
Wrap your Cypher query in 【CYPHER】...【/CYPHER】 tags.
Generate ONLY ONE executable query.
Do NOT include explanations or apologies.

Now generate the Cypher query for the given question:
"""

# ============ 缺口上下文查询Prompt（ID 模式：按 unique_id 精确定位边）============
GAP_CONTEXT_PROMPT = """你是一个Neo4j Cypher专家，服务于自动驾驶场景视觉问答出题系统。

{schema}

任务：给定一条**尚未被任何题目覆盖的具体场景图边（由 src_id 和 tgt_id 唯一确定）**，
生成一条 Cypher 查询，精确定位该边并获取出题所需的完整上下文（含 L2 前/后置链节点）。

目标边信息：
  src_id     : {src_id}       （源节点唯一ID，用于精确匹配）
  src_type   : {src_type}
  src_status : {src_status}
  tgt_id     : {tgt_id}       （目标节点唯一ID，用于精确匹配）
  tgt_type   : {tgt_type}
  tgt_status : {tgt_status}
  方向(4方位): {dir4}
  方向(8方位): {dir8}
  距离级别   : {dist_level}

需要在一条 Cypher 中完成：
1. 按 src_id / tgt_id 精确定位该边。
2. 返回两端节点的 unique_id / type / status，以及边的方向和距离级别。
3. [L2-类型A] OPTIONAL MATCH: 找一个前置锁点 anchor，满足 anchor→src（anchor ≠ tgt），
   返回 anchor 的 unique_id / type / status 以及 anchor→src 边的方向。
4. [L2-类型B] OPTIONAL MATCH: 找一个后置节点 beyond，满足 tgt→beyond（beyond ≠ src），
   返回 beyond 的 unique_id / type / status 以及 tgt→beyond 边的方向。

返回字段别名（严格按此命名，缺失字段返回 null）：
  src_id, src_type, src_status,
  tgt_id, tgt_type, tgt_status,
  dir4, dir8, dist_level,
  anc_id, anc_type, anc_status, anc_dir4, anc_dir8,
  beyond_id, beyond_type, beyond_status, beyond_dir4, beyond_dir8

约束：
- 只生成一条查询，OPTIONAL MATCH 用于 L2 扩展。
- OPTIONAL MATCH 按距离 ASC 选最近节点。
- LIMIT 1。

示例（src_id='car3', tgt_id='ped2'）：
【CYPHER】
MATCH (src:Object {{unique_id: 'car3'}})-[r:RELATES_TO]->(tgt:Object {{unique_id: 'ped2'}})
OPTIONAL MATCH (anc:Object)-[r0:RELATES_TO]->(src)
WHERE anc.unique_id <> tgt.unique_id
OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
WHERE beyond.unique_id <> src.unique_id
WITH src, tgt, r, anc, r0, beyond, r2
ORDER BY
  CASE WHEN anc    IS NOT NULL THEN r0.distance ELSE 9999 END ASC,
  CASE WHEN beyond IS NOT NULL THEN r2.distance ELSE 9999 END ASC
LIMIT 1
RETURN
  src.unique_id AS src_id, src.type AS src_type, src.status AS src_status,
  tgt.unique_id AS tgt_id, tgt.type AS tgt_type, tgt.status AS tgt_status,
  r.direction_4 AS dir4, r.predicates[0] AS dir8, r.predicates[1] AS dist_level,
  anc.unique_id AS anc_id, anc.type AS anc_type, anc.status AS anc_status,
  r0.direction_4 AS anc_dir4, r0.predicates[0] AS anc_dir8,
  beyond.unique_id AS beyond_id, beyond.type AS beyond_type, beyond.status AS beyond_status,
  r2.direction_4 AS beyond_dir4, r2.predicates[0] AS beyond_dir8
【/CYPHER】

现在为以下目标边生成查询（严格按上述格式，只输出 Cypher，不加任何解释）：
"""

# ============ 场景图初始分析Prompt（枚举所有边实例，含唯一 ID）============
SCENE_ANALYSIS_PROMPT = """你是一个Neo4j Cypher专家。

{schema}

任务：生成一条 Cypher 查询，枚举当前场景图中所有存在的具体边，
返回每条边的源/目标节点唯一 ID、类型、状态及边方向/距离，
作为覆盖率 KV map（以 edge ID 对为 key）的初始化中间量。

返回字段：
  src_id, src_type, src_status, tgt_id, tgt_type, tgt_status,
  dir4, dir8, dist_level

约束：
- status / dist_level 为 null 时，用 coalesce 转为空字符串 ''。
- 不加 LIMIT，返回所有边。

示例输出：
【CYPHER】
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
RETURN
  src.unique_id AS src_id,
  src.type AS src_type,
  coalesce(src.status, '') AS src_status,
  tgt.unique_id AS tgt_id,
  tgt.type AS tgt_type,
  coalesce(tgt.status, '') AS tgt_status,
  r.direction_4 AS dir4,
  r.predicates[0] AS dir8,
  coalesce(r.predicates[1], '') AS dist_level
【/CYPHER】

现在生成查询（只输出 Cypher，不加任何解释）：
"""

# ============ 结果转答案Prompt ============
RESULT_TO_ANSWER_PROMPT = """Convert Neo4j query result to natural language answer.

Question: {question}
Question Type: {question_type}
Query Result: {result}
Format Requirement: {format_requirement}

Rules:
1. Extract the core answer directly from the result
2. For yes/no questions: answer "yes" or "no"
3. For count questions: answer the number
4. For status questions: answer the status value (e.g., "stopped", "with_rider")
5. For object questions: answer the object type (e.g., "car", "bicycle")
6. Keep the answer concise and direct
7. If result is empty or count is 0, answer "no" for existence questions

Answer:"""

