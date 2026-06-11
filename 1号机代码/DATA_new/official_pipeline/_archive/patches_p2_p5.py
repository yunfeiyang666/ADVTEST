"""
patches_p2_p5.py — 剩余优化补丁汇总(P2/P3/P4/P5)
==================================================
本文件不是可执行脚本,是一份**精确到行的改动说明**,给你和 agent 对着改。
每个 patch 独立,可以按任意顺序应用。

生成时间: 2026-04-12
基于代码: run_method_a.py (957行) + coverage_tracker.py (409行)
"""

# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P2: failed cell 退避(cooldown)
# 文件: run_method_a.py
# 说明: 当前已有 fail_counts + unresolvable(MAX_FAIL=3 次后永久拉黑),
#       但问题是:永久拉黑的 cell 永远不会再被尝试,即使后续约束链修好了也不行。
#       更好的策略是"cooldown 而非永久拉黑",且增加"连续空轮→自然终止"。
#
# 实际上看完代码,run_method_a.py 已经有 fail_counts/unresolvable/MAX_FAIL=3 机制,
# 这和我之前设计的 cooldown 方案功能等价。唯一缺的是"连续空轮自然终止",
# 但这已经由 VQA_MAX_EMPTY_STREAK 覆盖了。
#
# → P2 实际上已经到位,不需要额外改动。确认即可。
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P3: drop-qtype 语义审计修复
# 文件: run_method_a.py
# 位置: _qtype_semantic_ok 函数 (约第 456 行)
# ═══════════════════════════════════════════════════════════════════════════════
#
# 当前问题:
#   1. status 题要求 q.startswith("what ") AND "status" in q
#      → 但很多 status 题的问题是 "What is the moving car doing?" 不含 "status" 字样
#   2. comparison 题要求 "closer"/"farther"/"further"
#      → 但 comparison 题的问题常常是 "Do the X and Y have the same status?" 不含这些词
#   3. exist 题只认 "is there"/"are there"
#      → 但 yesno_fallback 生成的问题常是 "Is the car moving behind..." 不以 "is there" 开头
#   4. object 题过于宽泛, q.startswith("what ") 会和 status 冲突
#
# 修法: 放宽判据,同时对 fallback 方法直接放行
#
# ---- 原代码 ----
#     def _qtype_semantic_ok(q_type: str, question: str) -> bool:
#         q = " ".join(str(question or "").strip().lower().split())
#         if not q:
#             return False
#         if q_type == "count":
#             return q.startswith("how many ")
#         if q_type == "exist":
#             return q.startswith("is there ") or q.startswith("are there ")
#         if q_type == "status":
#             return "status" in q and q.startswith("what ")
#         if q_type == "comparison":
#             return ("closer" in q) or ("farther" in q) or ("further" in q)
#         # object
#         return (
#             q.startswith("what ")
#
# ---- 改后代码 ----
#     def _qtype_semantic_ok(q_type: str, question: str, method: str = "") -> bool:
#         """语义审计:问题文本是否匹配 q_type。对 fallback 方法放行。"""
#         # fallback 方法的题是降级题,文本模板不需要严格匹配
#         if method in ("yesno_fallback", "count_fallback", "emergency_fallback"):
#             return True
#
#         q = " ".join(str(question or "").strip().lower().split())
#         if not q:
#             return False
#         if q_type == "count":
#             return q.startswith("how many ")
#         if q_type == "exist":
#             # 放宽: "is there" / "are there" / "is the" / "are the" / "does"
#             return (q.startswith("is there ") or q.startswith("are there ")
#                     or q.startswith("is the ") or q.startswith("is a ")
#                     or q.startswith("are the ") or q.startswith("does "))
#         if q_type == "status":
#             # 放宽: 含 "status" 或以 "what" 开头问状态相关
#             return q.startswith("what ") and (
#                 "status" in q or "moving" in q or "stopped" in q
#                 or "parked" in q or "doing" in q or "state" in q
#             )
#         if q_type == "comparison":
#             # 放宽: 含比较词 或 "same" / "different"
#             return ("closer" in q or "farther" in q or "further" in q
#                     or "same" in q or "different" in q
#                     or "do the" in q or "does the" in q)
#         # object: startswith "what" 但不是 count/status
#         return q.startswith("what ")
#
# ---- 调用处也要改(传入 method) ----
# 位置: 约第 683 行的 _qtype_semantic_ok 调用
#
# 原: if _qtype_semantic_ok(_q_type, _question):
# 改: if _qtype_semantic_ok(_q_type, _question, method=_method):


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P4: 幽灵路径探测(coverage_tracker.py) —— 已在仓库落地
# 文件: gap_pipeline/coverage_tracker.py
# 实现名: CoverageTracker._prune_phantom_l2_paths(session)
# 调用: init_from_session() 在 L2B 填充后调用,并打 WARNING 汇总 L2A/L2B prune 数量
# ═══════════════════════════════════════════════════════════════════════════════
#
# 问题: L2B 枚举有 LIMIT 3000,采样到的路径可能在当前过滤图上不存在
#       (或者 init 时的图和后续 gap 生成时的图不一致)
#
# 若你看到的是旧说明里的 _prune_phantom_paths,与当前 _prune_phantom_l2_paths 等价
#
# ---- 在 class CoverageTracker 内追加 ----
#
#     def _prune_phantom_paths(self, session) -> None:
#         """移除在当前 Neo4j 图上实际不存在的 L2 路径。"""
#         for store, meta_store, level in [
#             (self._L2A, self._L2A_meta, "L2A"),
#             (self._L2B, self._L2B_meta, "L2B"),
#         ]:
#             phantom_keys = []
#             for key in store:
#                 n1, n2, n3 = key.split("|")
#                 cypher = (
#                     "MATCH (a:Object {unique_id:$n1})"
#                     "-[:RELATES_TO]->(b:Object {unique_id:$n2})"
#                     "-[:RELATES_TO]->(c:Object {unique_id:$n3})"
#                     " RETURN 1 LIMIT 1"
#                 )
#                 result = session.run(cypher, n1=n1, n2=n2, n3=n3).single()
#                 if result is None:
#                     phantom_keys.append(key)
#
#             for k in phantom_keys:
#                 store.pop(k, None)
#                 meta_store.pop(k, None)
#
#             if phantom_keys:
#                 logger.warning(
#                     "Pruned %d phantom %s paths (not in current graph)",
#                     len(phantom_keys), level
#                 )
#
# ---- 在 init_from_session 末尾加一行 ----
# 位置: 约第 189 行 logger.info("CoverageTracker initialised...") 之前
#
#         self._prune_phantom_paths(session)
#
# 性能: 3000 条 × ~5ms = ~15秒,一帧只做一次,完全可接受。
# 如果嫌慢,可以改成 UNWIND 批量查:
#
#     def _prune_phantom_paths_batch(self, session, batch_size=200):
#         for store, meta_store, level in [
#             (self._L2A, self._L2A_meta, "L2A"),
#             (self._L2B, self._L2B_meta, "L2B"),
#         ]:
#             all_keys = list(store.keys())
#             phantom = []
#             for i in range(0, len(all_keys), batch_size):
#                 batch = all_keys[i:i+batch_size]
#                 triples = [k.split("|") for k in batch]
#                 cypher = """
#                 UNWIND $triples AS t
#                 OPTIONAL MATCH (a:Object {unique_id:t[0]})
#                   -[:RELATES_TO]->(b:Object {unique_id:t[1]})
#                   -[:RELATES_TO]->(c:Object {unique_id:t[2]})
#                 RETURN t[0]+'|'+t[1]+'|'+t[2] AS key, count(c) AS n
#                 """
#                 for rec in session.run(cypher, triples=triples):
#                     if rec["n"] == 0:
#                         phantom.append(rec["key"])
#             for k in phantom:
#                 store.pop(k, None)
#                 meta_store.pop(k, None)
#             if phantom:
#                 logger.warning("Pruned %d phantom %s paths", len(phantom), level)


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P5a: MIN_ITER_COUNT 默认值 2 → 1
# 文件: run_method_a.py
# 位置: 约第 399 行
# ═══════════════════════════════════════════════════════════════════════════════
#
# 原: MIN_ITER_COUNT = int(os.getenv("VQA_MIN_ITER_COUNT", "2"))
# 改: MIN_ITER_COUNT = int(os.getenv("VQA_MIN_ITER_COUNT", "1"))
#
# 理由: iter=1 代表一次命中(直接用第一个约束方法就唯一了),不应被惩罚。
# 环境变量仍可覆盖。


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P5b: ctx={} → 传真实 ctx + referents(恢复 TwoHopReferent/DualHopReferent)
# 文件: run_gap_pipeline_v6.py 的 _process_single_cell
# 协调说明(与 constraint_methods 对齐):
#   · TwoHopReferent / DualHopReferent 需要 ref_id/ref_type/dir8/sibling_cnt/sibling_ids
#   · 仅 append {"id": sid} 无法让 find_value 命中(sibling_cnt 默认 99)
#   · 应在 V6 中复用 run_gap_pipeline._fetch_referents(session, tgt_id=n3, src_id=n2, tgt_type=n3_type)
#     其中 src_id 取路径上 n3 的直接前驱 n2(与 V5「排除指向 tgt 的已知父节点」语义一致),勿误用 n1
# ═══════════════════════════════════════════════════════════════════════════════
#
# 当前问题:
#   tighten() 调用时 ctx={},导致:
#     - P11 TwoHopReferent (can_apply 检查 ctx["referents"]) → 永远 False
#     - P14 DualHopReferent (同上) → 永远 False
#   你原设计里 P11 命中率 42%,P14 命中率 16%,现在都是 0%。
#
# 修法: 把 _process_single_cell 里或调用处的 ctx 从 {} 改成包含 referents
#
# 位置 (run_method_a.py 约第 610 行):
#     _qa, _timing = _process_single_cell(
#         cell=_cell, topology=_topology, cypher=_cypher,
#         driver=driver, chain=_local_chain,
#         scene_name=SCENE_ID, frame_idx=FRAME_ID,
#         llm_timing=dict(_llm.last_call_timing),
#         render_local_question=False,
#     )
#
# _process_single_cell 内部调用 tighten 时传的 ctx:
#     tighten = chain.tighten(
#         gap_target=gap_target, candidates=candidates, tvars=tvars, ctx={},
#     )
#
# 改成:
#     tighten = chain.tighten(
#         gap_target=gap_target, candidates=candidates, tvars=tvars, ctx=ctx,
#     )
#
# 其中 ctx 是 _process_single_cell 已经从 Neo4j 查回来的上下文字典,
# 里面已经有 sibling_ids / sibling_types / sibling_dir8s 等字段。
# 但它**没有 referents 字段**——referents 是 TwoHopReferent 专用的,
# 需要从 ctx["sibling_ids"] 里进一步构造。
#
# 具体做法: 在 _process_single_cell 里, 构造完 candidates 和 gap_target 之后,
# 给 ctx 补上 referents:
#
#     # 构造 referents: sibling 中与目标有共同邻居的节点
#     referents = []
#     for sid in ctx.get("sibling_ids", []):
#         if sid and sid != n3:
#             referents.append({"id": sid})
#     ctx["referents"] = referents
#     ctx["src_status"] = ctx.get("n1_status", "")
#
# 注意: 这是最简版本。TwoHopReferent 的 can_apply 只检查 bool(ctx["referents"]),
# find_value 则需要在 referents 里找到一个 R 使得 "R→B 唯一指向目标"。
# 如果 referents 列表里没有满足条件的,find_value 会返回 None,
# 链自然继续下一个方法。所以传个不完美的 referents 列表也不会出错,
# 只是可能命中率比 42% 低一些——但肯定比 0% 好。
#
# ⚠️ 此 patch 影响较大(可能改变约束链的命中分布),建议最后做,且先在单帧
#   验证后再部署到服务器。


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH P5c: LOW_ITER_STRICT_METHODS 默认值清理
# 文件: run_method_a.py
# 位置: 约第 401 行
# ═══════════════════════════════════════════════════════════════════════════════
#
# 原: LOW_ITER_STRICT_METHODS = {
#         x.strip() for x in os.getenv("VQA_MIN_ITER_STRICT_METHODS",
#                                       "no_constraint_needed,path").split(",")
#     }
#
# "no_constraint_needed" 已被 M1 禁用,这个默认值里的它已无意义。
# 改成只保留 "path"(或直接清空):
#
# 改: LOW_ITER_STRICT_METHODS = {
#         x.strip() for x in os.getenv("VQA_MIN_ITER_STRICT_METHODS",
#                                       "path").split(",")
#         if x.strip()
#     }


# ═══════════════════════════════════════════════════════════════════════════════
# 汇总: 改动优先级和预期效果
# ═══════════════════════════════════════════════════════════════════════════════
#
# | Patch | 改动量 | 预期效果 | 优先级 |
# |-------|--------|----------|--------|
# | P2    | 0行(已有) | 确认即可 | ✅ done |
# | P3    | ~25行  | drop-qtype 从 15% 降到 <5% | 高 |
# | P4    | ~30行  | 消除幽灵路径导致的无效 FAIL | 高 |
# | P5a   | 1行    | drop-low-iter 归零 | 高 |
# | P5b   | ~5行   | TwoHopReferent 恢复(42%命中率) | 中(先单帧验证) |
# | P5c   | 1行    | 清理死代码 | 低 |
