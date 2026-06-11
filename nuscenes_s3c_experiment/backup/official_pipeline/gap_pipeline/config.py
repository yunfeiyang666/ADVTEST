"""
Gap Pipeline — Configuration
LLM settings + ID-based scene-analysis and gap-context prompts.
"""
import os

# ==================== LLM 配置 ====================
LLM_CONFIG = {
    "api_key":  os.getenv("VQA_API_KEY",      ""),
    "api_base": os.getenv("VQA_API_BASE_URL", "http://218.197.140.7:3001/v1"),
    # 兼容旧配置：VQA_MODEL_NAME 仍可作为统一模型入口
    "model":    os.getenv("VQA_MODEL_NAME",   "Qwen3.5-35B-A3B"),
    # V23: 双模型分工（可选）
    # - 审计/意图提取/Cypher 生成：model_audit
    # - 自然语言问题渲染：model_render
    # 若未显式提供，则回退到统一 model（当前默认 35B；不强依赖 122B）。
    "model_audit":  os.getenv("VQA_MODEL_AUDIT",  os.getenv("VQA_MODEL_NAME", "Qwen3.5-35B-A3B")),
    "model_render": os.getenv("VQA_MODEL_RENDER", os.getenv("VQA_MODEL_NAME", "Qwen3.5-35B-A3B")),
    "verify_ssl": os.getenv("VQA_VERIFY_SSL", "false").lower() in ("true", "1"),
    "trust_env_proxy": os.getenv("VQA_TRUST_ENV_PROXY", "false").lower() in ("true", "1", "yes"),
    "disable_thinking": os.getenv("VQA_DISABLE_THINKING", "true").lower() in ("true", "1", "yes"),
    "temperature": 0.0,
    "max_tokens": 400,
    "timeout_connect": 10.0,
    "timeout_read":    30.0,  # qwen-plus 实测 ~6s，30s 留足够余量
}

# ==================== 场景全量边枚举 Prompt ====================
# LLM 返回一条 Cypher，逐边枚举场景图中所有有向边，
# 每行返回: src_id, src_type, src_status, tgt_id, tgt_type, tgt_status, dir4, dir8, dist_level
# ==================== 论文对齐常量 ====================
# NuScenes-QA (AAAI 2024) 6 方向划分（论文 Eq.(2)）
DIRECTION_PREDICATES_8 = {
    "front":       (-30.0,   30.0),   # -30° < θ <= 30°
    "front-left":  ( 30.0,   90.0),   # 30° < θ <= 90°
    "front-right": (-90.0,  -30.0),   # -90° < θ <= -30°
    "back-left":   ( 90.0,  150.0),   # 90° < θ <= 150°
    "back-right":  (-150.0, -90.0),   # -150° < θ <= -90°
    "back":        (150.0, -150.0),   # else (wrap)
}
# 原论文不定义 near/mid/far 离散距离；此处仅保留为内部辅助字段（非关系主定义）。
DIST_THRESHOLDS = {"near": (0, 10), "mid": (10, 25), "far": (25, float("inf"))}

SCENE_ANALYSIS_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

The graph contains:
  - Nodes with properties: unique_id (string), type (string), status (string)
  - Directed edges with properties:
      dir4       (one of: front / left / right / back)
      dir8       (one of: front / front-left / front-right /
                          back-left / back-right / back)
      dist_level (one of: near / mid / far)

Task:
Write a Cypher query that enumerates EVERY directed edge in the graph and returns
exactly these nine columns (in this order):
  src_id, src_type, src_status,
  tgt_id, tgt_type, tgt_status,
  dir4, dir8, dist_level

Rules:
- One row per edge — do NOT aggregate or GROUP BY.
- Include ALL edges, not only ego-originated ones.
- Column aliases must match the list exactly.

Return ONLY the Cypher query, no explanation or markdown fences.
"""

# ==================== 缺口上下文 Cypher 生成 Prompt ====================
# 给定 gap cell 的 src_id / tgt_id / dir8，
# LLM 返回一条精确定位该边并拉取单跳扩展上下文的 Cypher（LIMIT 1）。
GAP_CONTEXT_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

Coverage gap to resolve:
  src_id = {src_id}
  tgt_id = {tgt_id}
  dir8   = {dir8}

Graph schema (use EXACTLY these property names):
  Node  :Object   {{ unique_id, type, status }}
  Edge  :RELATES_TO {{
    direction_4   (front/left/right/back),
    direction_8   (front/front-left/front-right/back-left/back-right/back),
    predicates    (list; predicates[1] is the distance level: near/mid/far),
    distance      (float, metres),
    direction_8   same as above
  }}

Write a Cypher query that:
1. Exactly matches the source node:  {{unique_id: '{src_id}'}}
2. Exactly matches the target node:  {{unique_id: '{tgt_id}'}}
3. Finds the directed :RELATES_TO edge between them.
4. OPTIONAL MATCH one ancestor of src  (a node with an edge TO src, excluding tgt).
5. OPTIONAL MATCH one node beyond tgt  (a node tgt has an edge TO, excluding src),
   preferring the same direction_8 as the main edge.
6. OPTIONAL MATCH ego's edge to tgt to capture ego_dir8.
7. Returns exactly these aliases (all in one row, LIMIT 1):
     src_id, src_type, src_status,
     tgt_id, tgt_type, tgt_status,
     dir4, dir8, dist_level, actual_dist, ego_dir8,
     anc_id, anc_type, beyond_id, beyond_type

Use this exact template (fill in {src_id} and {tgt_id}):

  MATCH (src:Object {{unique_id: '{src_id}'}})-[e:RELATES_TO]->(tgt:Object {{unique_id: '{tgt_id}'}})
  OPTIONAL MATCH (anc:Object)-[:RELATES_TO]->(src)
    WHERE anc.unique_id <> tgt.unique_id
  WITH src, tgt, e, collect(anc)[0] AS anc
  OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
    WHERE beyond.unique_id <> src.unique_id
      AND r2.direction_8 = e.direction_8
  WITH src, tgt, e, anc, collect(beyond)[0] AS beyond
  OPTIONAL MATCH (:Object {{unique_id: 'ego'}})-[ego_r:RELATES_TO]->(tgt)
  RETURN
    src.unique_id                    AS src_id,
    src.type                         AS src_type,
    coalesce(src.status, '')         AS src_status,
    tgt.unique_id                    AS tgt_id,
    tgt.type                         AS tgt_type,
    coalesce(tgt.status, '')         AS tgt_status,
    e.direction_4                    AS dir4,
    e.direction_8                    AS dir8,
    coalesce(e.predicates[1], '')    AS dist_level,
    e.distance                       AS actual_dist,
    coalesce(ego_r.direction_8, '')  AS ego_dir8,
    anc.unique_id                    AS anc_id,
    anc.type                         AS anc_type,
    beyond.unique_id                 AS beyond_id,
    beyond.type                      AS beyond_type
  LIMIT 1

You may add extra OPTIONAL MATCH clauses to enrich the context, but do NOT change
the RETURN aliases or omit any of the listed columns.
Return ONLY the Cypher query, no explanation or markdown fences.
"""

# ==================== L2A 路径缺口上下文 Prompt ====================
# 给定三节点锚点链路径缺口 ego→A→B，
# LLM 责任：列出 A 指向的全部干扰项（B 的兄弟节点），
# 这些干扰项是 ConstraintChain 锁定 B 的压力源。
L2A_CONTEXT_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

L2A chain path gap:
  Leg 1: ego  ({n1_id})  →  {n2_type} ({n2_id})   direction={r1_dir8}
  Leg 2: {n2_type} ({n2_id})  →  {n3_type} ({n3_id})   direction={r2_dir8}

Graph schema (use EXACTLY these property names):
  Node  :Object   {{ unique_id, type, status }}
  Edge  :RELATES_TO {{
    direction_4   (front/left/right/back),
    direction_8   (front/front-left/front-right/back-left/back-right/back),
    predicates    (list; predicates[1] = dist_level: near/mid/far),
    distance      (float, metres)
  }}

Write a Cypher that:
1. Matches the exact 2-hop path:
   MATCH (ego:Object {{unique_id:'{n1_id}'}})-[r1:RELATES_TO]->(a:Object {{unique_id:'{n2_id}'}})
         -[r2:RELATES_TO]->(b:Object {{unique_id:'{n3_id}'}})
2. OPTIONAL MATCH all INTERFERENCE SIBLINGS: other nodes that {n2_id} also points to
   (exclude ego and b itself). These are the confounders that prove B is NOT trivially unique.
   OPTIONAL MATCH (a)-[r3:RELATES_TO]->(sibling:Object)
     WHERE sibling.unique_id <> '{n1_id}' AND sibling.unique_id <> '{n3_id}'
3. Collect siblings as map array to preserve per-sibling spatial data:
   WITH a, b, r1, r2,
        collect({{id:sibling.unique_id, type:sibling.type,
                  status:coalesce(sibling.status,''),
                  dir8:r3.direction_8, dist:r3.distance}}) AS siblings
4. Returns exactly (one row, LIMIT 1):
   'ego'                            AS n1_id,
   a.unique_id AS n2_id, a.type AS n2_type, coalesce(a.status,'') AS n2_status,
   b.unique_id AS n3_id, b.type AS n3_type, coalesce(b.status,'') AS n3_status,
   r1.direction_4 AS r1_dir4, r1.direction_8 AS r1_dir8,
   coalesce(r1.predicates[1],'') AS r1_dist,  r1.distance AS r1_actual_dist,
   r2.direction_4 AS r2_dir4, r2.direction_8 AS r2_dir8,
   coalesce(r2.predicates[1],'') AS r2_dist,  r2.distance AS r2_actual_dist,
   [s IN siblings | s.id]     AS sibling_ids,
   [s IN siblings | s.type]   AS sibling_types,
   [s IN siblings | s.status] AS sibling_statuses,
   [s IN siblings | s.dir8]   AS sibling_dir8s,
   [s IN siblings | s.dist]   AS sibling_dists

Return ONLY the Cypher query, no explanation or markdown fences.
"""

# ==================== L2B 物体链上下文 Prompt (V5) ====================
# V5 重定义 L2B: A→B→C 物体起始链（全部非主车）
# LLM 责任：匹配完整三节点路径，并返回 B 的干扰项兄弟节点
L2B_OBJ_CONTEXT_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

L2B object-centric chain path gap (NO ego involved):
  Leg 1: {n1_type}({n1_id})  →  {n2_type}({n2_id})   direction={r1_dir8}
  Leg 2: {n2_type}({n2_id})  →  {n3_type}({n3_id})   direction={r2_dir8}
  (A, B, C are all traffic objects, NOT the ego/host vehicle)

Graph schema (exact property names):
  Node  :Object   {{ unique_id, type, status }}
  Edge  :RELATES_TO {{
    direction_4, direction_8,
    predicates (list; [1]=dist_level: near/mid/far),
    distance   (float, metres)
  }}

Write a Cypher that:
1. Matches the exact 2-hop non-ego path:
   MATCH (a:Object {{unique_id:'{n1_id}'}})-[r1:RELATES_TO]->(b:Object {{unique_id:'{n2_id}'}})
         -[r2:RELATES_TO]->(c:Object {{unique_id:'{n3_id}'}})
2. OPTIONAL MATCH INTERFERENCE SIBLINGS:
   OPTIONAL MATCH (b)-[r3:RELATES_TO]->(sibling:Object)
     WHERE sibling.unique_id <> '{n1_id}' AND sibling.unique_id <> '{n3_id}'
3. Collect siblings as map array (preserves per-sibling spatial info):
   WITH a, b, c, r1, r2,
        collect({{id:sibling.unique_id, type:sibling.type,
                  status:coalesce(sibling.status,''),
                  dir8:r3.direction_8, dist:r3.distance}}) AS siblings
4. Returns exactly (one row, LIMIT 1):
   a.unique_id AS n1_id, a.type AS n1_type, coalesce(a.status,'') AS n1_status,
   b.unique_id AS n2_id, b.type AS n2_type, coalesce(b.status,'') AS n2_status,
   c.unique_id AS n3_id, c.type AS n3_type, coalesce(c.status,'') AS n3_status,
   r1.direction_4 AS r1_dir4, r1.direction_8 AS r1_dir8,
   coalesce(r1.predicates[1],'') AS r1_dist, r1.distance AS r1_actual_dist,
   r2.direction_4 AS r2_dir4, r2.direction_8 AS r2_dir8,
   coalesce(r2.predicates[1],'') AS r2_dist, r2.distance AS r2_actual_dist,
   [s IN siblings | s.id]     AS sibling_ids,
   [s IN siblings | s.type]   AS sibling_types,
   [s IN siblings | s.status] AS sibling_statuses,
   [s IN siblings | s.dir8]   AS sibling_dir8s,
   [s IN siblings | s.dist]   AS sibling_dists

Return ONLY the Cypher query, no explanation or markdown fences.
"""

# ==================== L2 批处理 Prompt (V6) ====================
# 一次打包 N 个路径缺口，要求模型返回 JSON 数组
# 每项格式：[topology, n1_id, n2_id, n3_id, r1_dir8, r2_dir8, n2_type, n3_type]
L2_BATCH_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

Generate {n} context-fetch Cyphers, one per L2 path gap listed below.
Schema: Node :Object{{unique_id,type,status}}, Edge :RELATES_TO{{direction_4,direction_8,predicates[1]=dist_level(near/mid/far),distance}}

For EVERY path gap:
1. MATCH the exact 2-hop path: n1-[r1]->n2-[r2]->n3
2. OPTIONAL MATCH n2's siblings (exclude n1 and n3):
   OPTIONAL MATCH (n2_node)-[r3:RELATES_TO]->(sibling:Object)
     WHERE sibling.unique_id <> n1_id AND sibling.unique_id <> n3_id
3. Collect siblings as map array:
   WITH ..., collect({{id:sibling.unique_id,type:sibling.type,status:coalesce(sibling.status,''),
                       dir8:r3.direction_8,dist:r3.distance}}) AS siblings
4. RETURN (one row, LIMIT 1):
   n1_id, n2_id, n2_type, n2_status, n3_id, n3_type, n3_status,
   r1_dir4, r1_dir8, r1_dist, r1_actual_dist, r2_dir4, r2_dir8, r2_dist, r2_actual_dist,
   [s IN siblings|s.id] AS sibling_ids, [s IN siblings|s.type] AS sibling_types,
   [s IN siblings|s.status] AS sibling_statuses,
   [s IN siblings|s.dir8] AS sibling_dir8s, [s IN siblings|s.dist] AS sibling_dists

Path gaps (JSON array of [topology, n1_id, n2_id, n3_id, r1_dir8, r2_dir8, n2_type, n3_type]):
{gaps_json}

Return ONLY a JSON array of {n} Cypher strings, no explanation:
["MATCH ...", "MATCH ...", ...]
"""

# ==================== V15: NLP 问题生成 Prompt ====================
# 输入：拓扑路径 + 约束描述 + 题型
# 输出：一条符合 NuScenes-QA 风格的自然语言问题
QUESTION_GEN_PROMPT = """\
You are writing a VQA (Visual Question Answering) question for an autonomous driving benchmark.

Spatial path:
  Leg 1: {n1_label} ({n1_type}) \u2192 {n2_label} ({n2_type}) [direction: {r1_dir}]
  Leg 2: {n2_label} ({n2_type}) \u2192 {n3_id} ({n3_type}, status={n3_status}) [direction: {r2_dir}]
Constraint applied to uniquely identify {n3_id}: {constraint_desc}
Query type: {q_type}
Expected answer: {answer}

Write EXACTLY ONE natural language question of type "{q_type}".
Use the actual object type names (e.g., "car", "truck", "pedestrian") NOT placeholders like TYPE or DIRECTION.

1. Use ONLY these direction words: front / front-left / front-right / back-left / back-right / back
2. Be concise (max 25 words), grammatically correct
3. Type-specific patterns (use actual names from the path above):
   - exist     : "Is there a {n3_type} to the {r2_dir} of the {n2_type} that is to the {r1_dir} of {n1_label}?"
   - count     : "How many {n3_type}s are to the {r2_dir} of the {n2_type} to the {r1_dir} of {n1_label}?"
   - status    : "What is the status of the {n3_type} to the {r2_dir} of the {n2_type} to the {r1_dir} of {n1_label}?"
   - object    : "What {n3_type} is to the {r2_dir} of the {n2_type} that is to the {r1_dir} of {n1_label}?"
   - comparison: "Is the {n3_type} to the {r2_dir} of the {n2_type} closer to or farther from {n1_label} than the {n2_type} itself?"
4. Replace {{n1_label}}, {{n2_type}}, {{n3_type}}, {{r1_dir}}, {{r2_dir}} with the actual values from the path above
5. Vary the wording from the patterns above for naturalness

Return ONLY the question text. No explanation. No quotes.
"""

# ==================== V16: 批量问题生成 Prompt（极致精简，压缩RTT） ====================
# 输入: JSON数组 [[q_type, n1, n2_type, dir1, n3_type, dir2, answer], ...]
# 输出: ["q1","q2",...] 精确匹配输入数量
# V14单题Prompt(1131字符) → V16批量(~420字符) ，减封55%
QUESTION_GEN_BATCH_PROMPT_V16 = """\
Return JSON array of {n} questions only.
In: {inputs_json}
Each item = [qt,n1,n2,d1,n3,d2,a]
qt rules:
exist:Is there a n3 to the d2 of the n2 to the d1 of n1?
count:How many n3s are to the d2 of the n2 to the d1 of n1?
status:What is the status of the n3 to the d2 of the n2 to the d1 of n1?
object:What n3 is to the d2 of the n2 to the d1 of n1?
comparison:Is the n3 to the d2 of the n2 closer to or farther from n1 than the n2?
Use only {front,front-left,front-right,back-left,back-right,back}, <=20 words.
Output exactly {n} strings.
"""

# ==================== L2B 路径缺口上下文 Prompt ====================
# 给定交互链路径缺口 X←ego→Y，
# LLM 责任：返回 X、Y 的全量属性（含距离、方向）以及 ego 的其他局部节点上下文。
L2B_CONTEXT_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

L2B interaction path gap:
  Arm 1: ego ({ego_id}) → {a_type} ({a_id})  direction={r1_dir8}  dist={r1_dist}
  Arm 2: ego ({ego_id}) → {b_type} ({b_id})  direction={r2_dir8}  dist={r2_dist}

Graph schema (exact property names):
  Node  :Object   {{ unique_id, type, status }}
  Edge  :RELATES_TO {{
    direction_4, direction_8,
    predicates (list; [1]=dist_level),
    distance   (float, metres)
  }}

Write a Cypher that:
1. Matches BOTH ego→X and ego→Y:
   MATCH (ego:Object {{unique_id:'{ego_id}'}})-[r1:RELATES_TO]->(a:Object {{unique_id:'{a_id}'}}),
         (ego)-[r2:RELATES_TO]->(b:Object {{unique_id:'{b_id}'}})
2. OPTIONAL MATCH a third ego-adjacent object (ctx) to enrich comparison context:
   OPTIONAL MATCH (ego)-[r3:RELATES_TO]->(ctx:Object)
     WHERE ctx.unique_id <> '{a_id}' AND ctx.unique_id <> '{b_id}'
   (IMPORTANT: use <> comparisons, NOT the NOT IN [...] syntax)
3. Returns exactly (one row, LIMIT 1):
   a.unique_id                      AS a_id,
   a.type                           AS a_type,
   coalesce(a.status,'')            AS a_status,
   '{ego_id}'                       AS ego_id,
   b.unique_id                      AS b_id,
   b.type                           AS b_type,
   coalesce(b.status,'')            AS b_status,
   r1.direction_4                   AS r1_dir4,
   r1.direction_8                   AS r1_dir8,
   coalesce(r1.predicates[1],'')    AS r1_dist,
   r1.distance                      AS r1_actual_dist,
   r2.direction_4                   AS r2_dir4,
   r2.direction_8                   AS r2_dir8,
   coalesce(r2.predicates[1],'')    AS r2_dist,
   r2.distance                      AS r2_actual_dist,
   collect(distinct ctx.unique_id)  AS context_node_ids,
   collect(distinct ctx.type)       AS context_node_types

Return ONLY the Cypher query, no explanation or markdown fences.
"""
