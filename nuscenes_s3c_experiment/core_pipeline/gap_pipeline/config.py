"""
Gap Pipeline — Configuration
LLM settings + ID-based scene-analysis and gap-context prompts.
"""
import os

# ==================== LLM 配置 ====================
LLM_CONFIG = {
    "api_key":  os.getenv("VQA_API_KEY",      "sk-dJCFs6OwNoKpfovSqNcnyVE80vMwpRu9JFN5nTyKV9XE06Xz"),
    "api_base": os.getenv("VQA_API_BASE_URL", "https://yunwu.ai/v1"),
    "model":    os.getenv("VQA_MODEL_NAME",   "deepseek-v3"),
    "verify_ssl": os.getenv("VQA_VERIFY_SSL", "false").lower() in ("true", "1"),
    "temperature": 0.0,
    "max_tokens": 512,   # deepseek-v3 无思考链，数据已足够
    "timeout_connect": 10.0,
    "timeout_read":    60.0,  # v3 实测 ~3s，60s 允许子误空间
}

# ==================== 场景全量边枚举 Prompt ====================
# LLM 返回一条 Cypher，逐边枚举场景图中所有有向边，
# 每行返回: src_id, src_type, src_status, tgt_id, tgt_type, tgt_status, dir4, dir8, dist_level
SCENE_ANALYSIS_PROMPT = """\
You are a Neo4j Cypher expert for autonomous driving scene graphs.

The graph contains:
  - Nodes with properties: unique_id (string), type (string), status (string)
  - Directed edges with properties:
      dir4       (one of: front / left / right / back)
      dir8       (one of: front / front-left / left / back-left /
                          back / back-right / right / front-right)
      dist_level (one of: very_close / close / medium / far)

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
    direction_8   (front/front-left/left/back-left/back/back-right/right/front-right),
    predicates    (list; predicates[1] is the distance level: very_close/close/medium/far),
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
