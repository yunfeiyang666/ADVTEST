"""
VQA Pipeline 配置文件

改进内容：
- 支持环境变量覆盖（特别是敏感信息如API密钥）
- 添加类型注解
- 配置验证函数
- 更好的结构组织
"""
import os
import logging
from typing import Dict, List, Optional

# 配置日志
logger = logging.getLogger(__name__)


# ============ API配置 ============
# ❗ 敏感信息应通过环境变量配置，不应硬编码
API_BASE_URL: str = os.getenv(
    'VQA_API_BASE_URL',
    'https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1'
)
API_KEY: str = os.getenv(
    'VQA_API_KEY',
    'sk-ecd91655d033446b9ae8ea390e65d923'  # 默认值仅供开发使用
)
APP_ID: str = os.getenv(
    'VQA_APP_ID',
    '61cb0d25ba9049d284ff68f9941481be'
)
MODEL_NAME: str = os.getenv('VQA_MODEL_NAME', 'deepseek-r1')

# 请求配置
REQUEST_TIMEOUT: int = int(os.getenv('VQA_REQUEST_TIMEOUT', '120'))
MAX_RETRIES: int = int(os.getenv('VQA_MAX_RETRIES', '3'))
# SSL验证（本地调试时可设为False）
VERIFY_SSL: bool = os.getenv('VQA_VERIFY_SSL', 'false').lower() in ('true', '1', 'yes')

# ============ Neo4j配置 ============
NEO4J_URI: str = os.getenv('NEO4J_URI', 'bolt://localhost:7600')
NEO4J_USER: str = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD: str = os.getenv('NEO4J_PASSWORD', '87017563')

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

🔄 双坐标系方向属性（重要）:
  Ego Frame（基于ego车辆朝向）:
  - angle_ego: 以ego朝向为基准的角度
  - direction_8_ego: 精确8方位 (front/front-left/left/back-left/back/back-right/right/front-right)
  - angle_matches_ego: 方向匹配列表（宽松匹配，如['back', 'back-right']）
  
  Source Frame（基于source对象朝向）:
  - angle_source: 以source对象朝向为基准的角度
  - direction_8_source: 精确8方位
  - angle_matches_source: 方向匹配列表

方位选择规则:
- **默认优先宽松匹配**：'DIRECTION' IN r.angle_matches_ego
- 单一方位词(front/back/left/right) → 仍可用 'back' IN r.angle_matches_ego
- 复合方位词(front-left/back-right等) → 用 'back-right' IN r.angle_matches_ego
- **精确匹配仅在明确要求时使用**：r.direction_8_ego = 'back-right' 或 r.direction_8_source = 'back-right'

特殊类型:
- trailer: WHERE n.category CONTAINS 'trailer'
- truck(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- motorcycle: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'

方位语义(参照物关系):
"X to DIRECTION of Y" → Y是参照物，X是目标
Cypher: MATCH (Y)-[r:RELATES_TO]->(X) WHERE 'DIRECTION' IN r.angle_matches_ego
"""

# ============ IR 生成Prompt ============
IR_GENERATION_PROMPT = f"""You are a precise information extraction engine. Convert the question into a QueryPlan JSON.

Schema:
{SCENE_GRAPH_SCHEMA}

Output requirements:
- Output ONLY valid JSON (no markdown, no comments).
- Top-level keys: question_type, answer_property, target, reference, comparison.
- target/reference/comparison can be null if not needed.
- Entity keys: type, alias, status (optional), constraints (list), relations (list).
- Relation keys: direction, ref.
- direction uses snake_case for diagonals: front_left, front_right, back_left, back_right.
- Use type "thing" for "thing/other thing".
- Use status field for status constraints; keep constraints empty if unused.
"""

# ============ IR -> Cypher Prompt (LLM) ============
IR_TO_LLM_CYPHER_PROMPT = f"""You are a Neo4j Cypher query expert. Convert the QueryPlan JSON into ONE executable Cypher query.

Schema:
{SCENE_GRAPH_SCHEMA}

Rules:
- Nodes use label Object and properties unique_id, type, category, status.
- trailer: n.category CONTAINS 'trailer'
- truck (exclude trailer): n.type='truck' AND NOT n.category CONTAINS 'trailer'
- motorcycle: n.type='motorcycle' OR n.category CONTAINS 'motorcycle'
- Status uses n.status only. Do NOT use velocity/translation/rotation.
- Direction semantics: "X to DIR of Y" -> MATCH (Y)-[r:RELATES_TO]->(X).
- Default direction filter: 'dir' IN r.angle_matches_ego, where dir uses kebab-case (front-right). Convert IR snake_case to kebab-case.
- If relation includes direction_frame == 'source', use r.angle_matches_source.
- If relation includes direction_precision == 'direction_8', use r.direction_8_ego or r.direction_8_source (based on direction_frame).
- Use LIMIT 1 for "the X" or unique selection.
- Single query, single RETURN at the end.

QueryPlan JSON:
{{query_plan}}

Original question:
{{question}}

Output only the Cypher query.
"""

# ============ Cypher生成主Prompt (精简版) ============
QUESTION_TO_CYPHER_PROMPT = """Question: {question}
Previous Error: {prev_error}

【硬性规则-必须遵守】
trailer → n.category CONTAINS 'trailer'
truck → n.type='truck' AND NOT n.category CONTAINS 'trailer'
motorcycle → n.type='motorcycle' OR n.category CONTAINS 'motorcycle'
方位 → 'DIR' IN r.angle_matches_source (如 'back-right' IN r.angle_matches_source)
'X to DIR of Y' → MATCH (Y)-[r:RELATES_TO]->(X) WHERE 'DIR' IN r.angle_matches_source
status值: stopped/moving/with_rider/without_rider/standing
'the X' → 加 LIMIT 1
other things → type<>'barrier'

【禁止】
- r.predicates[0]
- velocity/translation/rotation
- 代码块内注释

【示例1】方位+状态查询
Q: stopped thing to the back of me
```cypher
MATCH (ego:Object {{unique_id:'ego'}})-[r:RELATES_TO]->(obj:Object)
WHERE obj.status='stopped' AND 'back' IN r.angle_matches_source
RETURN obj.type LIMIT 1
```

【示例2】with/without rider
Q: What is the with rider thing?
```cypher
MATCH (n:Object) WHERE n.status='with_rider'
RETURN n.type LIMIT 1
```

【示例3】计数
Q: How many cars are stopped?
```cypher
MATCH (c:Object {{type:'car'}}) WHERE c.status='stopped'
RETURN count(c) AS count
```

【示例4】same status比较
Q: same status as the truck?
```cypher
MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
WITH truck.status AS refStatus, truck.unique_id AS refId LIMIT 1
MATCH (other:Object) WHERE other.status=refStatus AND other.unique_id<>refId
RETURN count(other) AS count
```

输出格式:
```cypher
<你的查询>
```
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

# ============ 问题类型配置 ============
QUESTION_TYPES: List[str] = [
    'exist',       # 存在性问题（yes/no）
    'count',       # 计数问题（数字）
    'status',      # 状态问题（stopped/moving等）
    'object',      # 对象识别问题（car/truck等）
    'comparison',  # 比较问题（yes/no）
]

# 对象类型
OBJECT_TYPES: List[str] = [
    'ego', 'car', 'truck', 'bus', 'bicycle', 
    'pedestrian', 'barrier', 'motorcycle', 'trailer'
]

# 状态值
STATUS_VALUES: List[str] = [
    'stopped', 'moving', 'with_rider', 'without_rider', 
    'parked', 'standing', 'sitting', 'unknown'
]

# 方向值
DIRECTION_4: List[str] = ['front', 'back', 'left', 'right']
DIRECTION_8: List[str] = [
    'front', 'front-left', 'left', 'back-left', 
    'back', 'back-right', 'right', 'front-right'
]

# 距离级别
DISTANCE_LEVELS: Dict[str, tuple] = {
    'near': (0, 10),   # ≤10m
    'mid': (10, 25),   # 10-25m
    'far': (25, float('inf')),  # >25m
}


# ============ 配置验证 ============
def validate_config() -> bool:
    """验证配置是否有效"""
    errors = []
    
    # 检查API配置
    if not API_KEY or API_KEY.startswith('sk-xxx'):
        errors.append("API_KEY未配置或为占位符")
    
    if not API_BASE_URL:
        errors.append("API_BASE_URL未配置")
    
    # 检查Neo4j配置
    if not NEO4J_URI:
        errors.append("NEO4J_URI未配置")
    
    if not NEO4J_PASSWORD:
        errors.append("NEO4J_PASSWORD未配置")
    
    # 检查超时配置
    if REQUEST_TIMEOUT <= 0:
        errors.append(f"REQUEST_TIMEOUT必须为正数: {REQUEST_TIMEOUT}")
    
    if MAX_RETRIES < 0:
        errors.append(f"MAX_RETRIES必须为非负数: {MAX_RETRIES}")
    
    if errors:
        for error in errors:
            logger.error(f"配置错误: {error}")
        return False
    
    return True


def get_config_summary() -> Dict[str, str]:
    """获取配置摘要（隐藏敏感信息）"""
    return {
        'api_base_url': API_BASE_URL,
        'api_key': f"{API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) > 12 else "***",
        'model_name': MODEL_NAME,
        'neo4j_uri': NEO4J_URI,
        'neo4j_user': NEO4J_USER,
        'request_timeout': str(REQUEST_TIMEOUT),
        'max_retries': str(MAX_RETRIES),
    }


def print_config():
    """打印配置信息（隐藏敏感信息）"""
    summary = get_config_summary()
    logger.info("VQA Pipeline 配置:")
    for key, value in summary.items():
        logger.info(f"  {key}: {value}")

