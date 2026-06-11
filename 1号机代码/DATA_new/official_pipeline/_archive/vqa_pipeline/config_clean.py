"""
VQA Pipeline 配置文件 - 清晰分块版
使用明确的分隔符，便于提取和清洗
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

# ============ 场景图Schema（精简版）============
SCENE_GRAPH_SCHEMA = """Neo4j场景图Schema:

节点 (Label: Object):
- unique_id: 对象唯一标识 (如'ego', 'car1', 'pedestrian1')
- type: 对象类型 (ego/car/truck/bus/bicycle/pedestrian/barrier/motorcycle/trailer)
- category: NuScenes类别 (如'vehicle.car', 'vehicle.trailer', 'vehicle.motorcycle')
- status: 对象状态 (stopped/moving/with_rider/without_rider/parked/standing/unknown)
⚠️ 不存在translation/rotation/velocity等属性

关系 (Type: RELATES_TO):
- predicates: [方位, 距离级别]
  * predicates[0]: 8方位 'front'/'front-left'/'left'/'back-left'/'back'/'back-right'/'right'/'front-right'
  * predicates[1]: 距离级别 'near'(≤10m)/'mid'(10-25m)/'far'(>25m)
- direction_4: 4方位 'front'/'left'/'back'/'right' (±45°范围，每个90°)
- direction_8: 8方位，同predicates[0] (±22.5°范围，每个45°)
- distance: 精确距离（米）

方位选择规则:
- 单一方位词(front/back/left/right) → 使用 r.direction_4
  例: "truck to the back of me" → WHERE r.direction_4 = 'back'
- 复合方位词(front-left/back-right等) → 使用 r.predicates[0]
  例: "bicycle to the front-left" → WHERE r.predicates[0] = 'front-left'

特殊类型:
- trailer: WHERE n.category CONTAINS 'trailer'
- truck(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- motorcycle: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'

方位语义（参照物关系）:
"X to DIRECTION of Y" → Y是参照物，X是目标
Cypher: MATCH (Y)-[r:RELATES_TO]->(X) WHERE r.DIRECTION_FIELD='DIRECTION'
例: "truck to back right of bicycle"
    MATCH (bicycle)-[r:RELATES_TO]->(truck) WHERE r.predicates[0]='back-right'
"""

# ============ 主Prompt模板（使用清晰分块）============
QUESTION_TO_CYPHER_PROMPT = """你是Neo4j Cypher查询专家。根据自然语言问题生成Cypher查询。

【SCHEMA】
{schema}
【/SCHEMA】

【USER_QUESTION】
问题: {question}
类型: {question_type}
上次错误: {prev_error}
【/USER_QUESTION】

【CORE_RULES】
1. 对象类型: ego, car, truck, bus, bicycle, pedestrian, barrier, motorcycle, trailer
2. trailer查询: WHERE n.category CONTAINS 'trailer'
   truck查询(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
3. motorcycle查询: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'
4. "other things" 默认指: [ego,car,truck,bus,bicycle,motorcycle,trailer,pedestrian]，不含barrier
5. 状态查询用status属性: WHERE n.status='with_rider'/'stopped'等
6. ⚠️ 关键：定义WITH变量后必须在后续WHERE中使用！
   错误: WITH refStatus, refId ... WHERE o.type='car' RETURN count(o)  // 未使用
   正确: WITH refStatus, refId ... WHERE o.type='car' AND o.status=refStatus AND o.unique_id<>refId RETURN count(o)
7. 多候选时按距离排序: ORDER BY r.distance ASC LIMIT 1
【/CORE_RULES】

【DIRECTION_SEMANTICS】
- "X to DIR of Y" → Y是参照物: MATCH (Y)-[r]->(X) WHERE r.DIR_FIELD='DIR'
- 4方位词 → 用 r.direction_4
- 8方位词 → 用 r.predicates[0]
【/DIRECTION_SEMANTICS】

【OUTPUT_CONSTRAINTS】
1. 只生成一条查询，只有一个RETURN
2. 不允许RETURN后再有新的MATCH/RETURN
3. 用【CYPHER】...【/CYPHER】包裹查询
【/OUTPUT_CONSTRAINTS】

【PATTERN_A_COMPARISON】
问题形式: "Is status of OBJ1 to DIR1 of REF1 same as OBJ2 to DIR2 of REF2?"
Cypher模板:
MATCH (ref1:Object) WHERE REF1_CONSTRAINTS
MATCH (ref1)-[r1:RELATES_TO]->(obj1:Object) WHERE OBJ1_CONSTRAINTS AND DIR1
WITH ref1, obj1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (ref2:Object) WHERE REF2_CONSTRAINTS  
MATCH (ref2)-[r2:RELATES_TO]->(obj2:Object) WHERE OBJ2_CONSTRAINTS AND DIR2
WITH obj1, obj2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN obj1.status = obj2.status AS same_status
【/PATTERN_A_COMPARISON】

【PATTERN_B_SAME_STATUS】
问题形式: "How many other X have same status as REF_TARGET to DIR of REF?"
Cypher模板（注意必须使用refStatus和refId）:
MATCH (ref:Object) WHERE REF_CONSTRAINTS
MATCH (ref)-[r1:RELATES_TO]->(ref_target:Object) WHERE REF_TARGET_CONSTRAINTS AND DIR
WITH ref_target, r1 ORDER BY r1.distance ASC LIMIT 1
WITH ref_target.status AS refStatus, ref_target.unique_id AS refId

MATCH (other:Object)
WHERE other.type='TARGET_TYPE' 
  AND other.status=refStatus    // 必须使用refStatus
  AND other.unique_id<>refId     // 必须使用refId
RETURN count(other) AS count
【/PATTERN_B_SAME_STATUS】

【PATTERN_C_MULTI_ANCHOR】
问题形式: "What is thing to DIR1 of REF1 and DIR2 of REF2?"
Cypher模板:
MATCH (ref1:Object) WHERE REF1_CONSTRAINTS
MATCH (ref2:Object) WHERE REF2_CONSTRAINTS
MATCH (ref1)-[r1:RELATES_TO]->(target:Object) WHERE DIR1
MATCH (ref2)-[r2:RELATES_TO]->(target) WHERE DIR2
WITH target, r1, r2 ORDER BY r1.distance+r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status
【/PATTERN_C_MULTI_ANCHOR】

【EXAMPLE_1_COMPARISON】
问题: "Is status of bus to back right of not standing pedestrian same as bus to front of stopped trailer?"

CYPHER示例:
MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object) WHERE bus1.type='bus' AND r1.predicates[0]='back-right'
WITH ped, bus1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object) WHERE bus2.type='bus' AND r2.direction_4='front'
WITH bus1, bus2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN bus1.status=bus2.status AS same_status
【/EXAMPLE_1_COMPARISON】

【EXAMPLE_2_SAME_STATUS】
问题: "How many other bicycles same status as barrier to front left of bicycle?"

CYPHER示例（必须使用WITH变量）:
MATCH (refBike:Object) WHERE refBike.type='bicycle'
WITH refBike LIMIT 1
MATCH (refBike)-[r:RELATES_TO]->(barrierObj:Object)
WHERE barrierObj.type='barrier' AND r.predicates[0]='front-left'
WITH refBike, barrierObj, r ORDER BY r.distance ASC LIMIT 1
WITH barrierObj.status AS barrierStatus, refBike.unique_id AS refBikeId

MATCH (otherBike:Object)
WHERE otherBike.type='bicycle' 
  AND otherBike.status=barrierStatus    // 使用barrierStatus
  AND otherBike.unique_id<>refBikeId     // 使用refBikeId
RETURN count(otherBike) AS count
【/EXAMPLE_2_SAME_STATUS】

【EXAMPLE_3_MULTI_ANCHOR】
问题: "What is thing to back right of stopped trailer and back of stopped truck?"

CYPHER示例:
MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (truck:Object) WHERE truck.type='truck' AND truck.status='stopped' AND NOT truck.category CONTAINS 'trailer'
MATCH (trailer)-[r1:RELATES_TO]->(target:Object) WHERE r1.predicates[0]='back-right'
MATCH (truck)-[r2:RELATES_TO]->(target) WHERE r2.direction_4='back'
WITH target, r1, r2 ORDER BY r1.distance+r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status
【/EXAMPLE_3_MULTI_ANCHOR】

【EXAMPLE_4_OTHER_THINGS】
问题: "Are there other things that in same status as truck?"

CYPHER示例（必须使用refStatus和refId）:
MATCH (refTruck:Object) WHERE refTruck.type='truck' AND NOT refTruck.category CONTAINS 'trailer'
WITH refTruck.status AS refStatus, refTruck.unique_id AS refId LIMIT 1

MATCH (other:Object)
WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
  AND other.status=refStatus          // 使用refStatus
  AND (other.type<>'truck' OR other.unique_id<>refId)  // 使用refId
RETURN count(other)>0 AS exist
【/EXAMPLE_4_OTHER_THINGS】

【EXAMPLE_5_SIMPLE_COUNT】
问题: "How many barriers are to front of trailer?"

CYPHER示例:
MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer'
WITH trailer LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(barrier:Object) 
WHERE barrier.type='barrier' AND r.direction_4='front'
RETURN count(barrier) AS barrier_count
【/EXAMPLE_5_SIMPLE_COUNT】

【OUTPUT_FORMAT】
必须输出格式:
【CYPHER】
你的唯一一条查询
【/CYPHER】
【/OUTPUT_FORMAT】
"""

RESULT_TO_ANSWER_PROMPT = """你是一个专业的问答助手。根据Neo4j查询结果，生成自然语言答案。

原始问题: {question}
问题类型: {question_type}
查询结果: {result}

答案格式要求:
{format_requirement}

要求:
1. 严格按照格式要求回答
2. 不要添加任何解释或额外信息
3. 如果结果为空，对于exist/comparison问题回答"no"，其他问题回答"0"或"未找到"

答案:"""

# ============ IR生成 Prompt（保持不变）============
IR_GENERATION_PROMPT = """You are an information extraction engine for NuScenes VQA.

Your ONLY task is to convert ONE English question about a NuScenes scene into ONE JSON QueryPlan object.
Do NOT answer the question. Do NOT explain. Just output the JSON.

You will be given:
- question_type: one of {"status","exist","count","count_same_status","comparison","object"}
- question: ONE English question string.

Schema conventions:
- "trailer" is a SPECIAL type: use type="trailer" in IR, it will be converted to category-based query
- "motorcycle" is a distinct type: use type="motorcycle" in IR, backed by category "vehicle.motorcycle"
- "with rider thing" means bicycle with status "with_rider"
- "not standing pedestrian" means pedestrian with status not "standing" (do NOT drop the "not" in normalization)
- Directions: "front", "back", "left", "right", "front_left", "back_right", etc.

QueryPlan schema:
{
  "question_type": "status" | "exist" | "count" | "count_same_status" | "comparison" | "object",
  "answer_property": "status" | "type" | "count" | "exists" | "boolean",
  "target": ObjectExpr or null,
  "reference": ObjectExpr or null,
  "comparison": {
    "property": "status" | "type",
    "lhs": ObjectExpr,
    "rhs": ObjectExpr
  } or null
}

ObjectExpr (recursive):
{
  "type": OBJECT_TYPE,
  "status": STATUS_VALUE or null,
  "alias": SHORT_VAR_NAME,
  "constraints": [],
  "relations": [ RelationExpr, ... ]
}

Allowed types: "ego", "car", "truck", "bus", "bicycle", "pedestrian", "barrier", "trailer", "thing"
Allowed statuses: "moving", "stopped", "parked", "with_rider", "without_rider", "standing", "not_standing"
Allowed directions: "front", "back", "left", "right", "front_left", "front_right", "back_left", "back_right"

Output requirements:
- Only output the JSON object
- Do NOT wrap in markdown
- Ensure valid JSON (no trailing commas)

Now produce the QueryPlan JSON for the given question_type and question.
"""

IR_TO_CYPHER_PROMPT = """You are a Neo4j Cypher query expert. Generate a Cypher query based on the given QueryPlan IR.

Neo4j Schema:
- Node label: Object
- Node properties: unique_id, type, status, category, attributes
- Relationship: RELATES_TO with predicates[0]=direction, predicates[1]=distance_level

Type Handling:
- type="trailer": WHERE n.category CONTAINS 'trailer'
- type="truck": WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- type="thing": [ego,car,truck,bus,bicycle,motorcycle,trailer,pedestrian]

Direction Mapping:
- 8-way (front_left, back_right, etc.) → r.predicates[0]
- 4-way (front, back, left, right) → r.direction_4

QueryPlan IR:
{query_plan}

Original Question: {question}

Generate ONE executable Cypher query. Rules:
1. Only ONE RETURN clause at the end
2. For status queries, always use status property
3. For exist queries: RETURN count(x) > 0 AS exists
4. For count queries: RETURN count(x) AS count
5. For comparison: RETURN a.status = b.status AS same
6. Use LIMIT 1 when getting a single unique object

Output ONLY the Cypher query, no explanation.

Cypher:"""
