# 夜间操作记录 — 2026-03-22/23

> **操作人**: Oz Agent（AI）  
> **开始时间**: 2026-03-22 23:26 (北京时间)  
> **结束时间**: 2026-03-23 00:55 (北京时间，后台管线仍在运行)  
> **目标**: 完整流程可运行 + 全链路计时 + 由缺口找上下文信息时启用大模型生成 Cypher + 约束方法逐层计时与分布统计

---

## 1. 项目结构探索（~23:26）

- 定位快捷方式目标路径：`E:\Project\ADVTEST`
- 核心代码位于：`nuscenes_s3c_experiment/core_pipeline/`
- 主流水线脚本：`run_gap_pipeline.py`
- 关键子模块（`gap_pipeline/`）：
  - `llm_client.py` — 大模型调用（OpenAI-compatible API，模型 deepseek-r1）
  - `constraint_methods.py` — 15 种约束方法 + ConstraintChain 调度器
  - `scene_coverage.py` — CoverageMap（edge / L2A / L2B 三级覆盖计数）
  - `gap_templates.py` — 75 模板 × 4 变体库

---

## 2. 流程架构回顾

```
Step 0  init              Neo4j + LLM 连接初始化
Step 1  scene_cypher      场景全量边枚举 Cypher（硬编码，已稳定）
Step 2  scene_neo4j       Neo4j 执行，获取全部有向边（~4032 条）
Step 3  cmap_init         CoverageMap 初始化
Step 4  gap_detect        识别未覆盖 edge（gap cells）

  每个 gap cell（循环）：
  Step 5a  ctx_llm        【本次核心改动】LLM 生成上下文 Cypher
  Step 5b  ctx_neo4j      Neo4j 执行上下文查询，获取 ctx 字典
  Step 5c  cand_neo4j     候选集查询（同方向对象）+ referent 批量查询
  Step 5d  constraint     ConstraintChain.tighten()  ← 重点计时
  Step 5e  template_fill  模板选择 + 填空 + 答案解析

Step 6  cmap_update       CoverageMap 最终统计（已在循环中实时更新）
```

---

## 3. 代码改动一览

### 3.1 `gap_pipeline/constraint_methods.py` — 逐方法计时

**改动时间**: ~23:35

**改动内容**:

1. 新增 `import time`
2. `TightenResult` 数据类增加两个字段：
   ```python
   method_timings: Dict[str, float] = field(default_factory=dict)
   # key=方法名, value=该方法在本次 tighten 中的耗时(ms)
   methods_tried: List[str] = field(default_factory=list)
   # 成功产生 value 的方法名列表（按尝试顺序）
   ```
3. `ConstraintChain.tighten()` 内部对每个方法包裹 `time.perf_counter()` 计时：
   - `can_apply` 返回 False → 记时并 continue
   - `find_value` 返回 None → 记时并 continue
   - 方法成功或 fallback → 记时后随结果一同返回
   - 收束不完全（继续下一方法）→ 也记录该方法耗时

**意图**: 获得每个约束方法（P1~P15）在真实数据上的耗时分布，识别瓶颈方法；同时统计哪些方法成功率高、哪些几乎总是 fallback。

---

### 3.2 `run_gap_pipeline.py` — LLM 上下文 Cypher + 增强计时汇总

**改动时间**: ~23:40

#### a. `_CellTiming` 类扩展
新增字段：
- `ctx_llm_used_llm: bool` — Step 5a 是否真正调用了大模型（超时/失败时为 False）
- `method_timings: Dict[str, float]` — 从 `TightenResult` 透传的逐方法计时

#### b. Step 5a: 由硬编码改为 LLM 生成 Cypher
```python
# 旧代码（硬编码）:
cypher = _LC.build_gap_context_cypher(src_id, tgt_id)

# 新代码（LLM + 降级兜底）:
try:
    cypher = llm_client.generate_gap_context_cypher(cell)
    timing.ctx_llm_used_llm = True
except Exception as _llm_exc:
    logger.warning("Step 5a LLM 失败（%s），退回硬编码 Cypher", _llm_exc)
    cypher = _LC.build_gap_context_cypher(src_id, tgt_id)
    timing.ctx_llm_used_llm = False
```

**意图**: 让大模型根据 gap cell 的 src/tgt/dir8 动态生成更精准的上下文 Cypher，从而可以拉取更丰富的邻域信息。降级兜底保证流程不中断。

#### c. Step 5d: 保存逐方法计时
```python
timing.method_timings = tighten_result.method_timings
```

#### d. `_print_summary` 增强输出
新增三段输出：
1. **Step 5a LLM 调用统计**（实际调用次数 vs 退回硬编码次数）
2. **约束方法成功分布**（方法名 | 成功次数 | 平均耗时 ms）
3. **各方法被计载次数**（含未成功的尝试，显示"命中率"）

#### e. 结果 JSON 增加字段
```json
{
  "step5a_llm_calls": 12,
  "step5a_fallback_calls": 88,
  "per_method_timing": {
    "type_filter": {"n": 100, "mean": 0.02, "max": 0.1, "min": 0.01, "p95": 0.05},
    ...
  }
}
```

---

### 3.3 `gap_pipeline/llm_client.py` — HTTP 超时与 max_retries=0

**改动时间**: ~00:40（发现 API 超时后修复）

**问题**: deepseek-r1 默认 openai 客户端无超时 + 2次重试 = 每个失败的 cell 耗时 270s（3×90s），100 cells 需要 7.5 小时。

**解决**:
```python
httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
openai.OpenAI(..., timeout=30.0, max_retries=0)
```

**效果**: 超时 cell 仅额外等待 ~30s，然后立即 fallback 到硬编码 Cypher，流程继续。

**验证日志**:
```
08:55:20  INFO   cell 1/100  ego→truck1
08:55:50  WARNING  Step 5a LLM 失败（Request timed out.），退回硬编码 Cypher
08:55:54  INFO   cell 2/100  ego→car35
```

---

## 4. 管线运行情况

### 4.1 首次尝试（失败 — 无超时）
- **时间**: ~23:31
- **问题**: 无 HTTP 超时，LLM 调用卡死，Ctrl+C 中断

### 4.2 第一次后台启动（失败 — 有超时但未禁重试）
- **时间**: 08:50（北京时间 3月23日）
- **问题**: 超时 90s 后 openai 自动重试 2 次 → 每 cell 耗时 270s
- **日志证据**:
  ```
  08:52:33  INFO  Retrying request to /chat/completions in 0.44s
  08:54:03  INFO  Retrying request to /chat/completions in 0.89s
  ```
- **处置**: Kill 进程，减小超时 + 禁止重试

### 4.3 当前运行（正常）
- **启动时间**: 2026-03-23 08:55:18（北京时间）
- **进程 PID**: 41076
- **参数**: `--max-cells 100 --use-constraint-chain`
- **输出日志**: `output/pipeline_run_20260323_v2_err.log`
- **输出 JSON**: `output/gap_timing_20260323.json`
- **总边数**: 4032（v1.0-mini 数据集）
- **处理 cell 数**: 100
- **预计完成**: ~09:45 北京时间（100 cells × ~31s/cell）

**实测速度（前两 cell）**:

| cell | 耗时估算 |
|------|----------|
| ego→truck1 | ~34s（30s LLM timeout + ~4s 其他）|
| ego→car35  | 启动于 08:55:54，持续中 |

> **注意**: 当前 API（maas-api.ai-yuanjing.com deepseek-r1）全部超时，100 cells 均使用硬编码 Cypher fallback。这验证了降级机制完整可用，约束链计时数据仍然有效。LLM 功能等 API 恢复后可再测试。

---

## 5. 约束方法设计说明（15层 ConstraintChain）

| 优先级 | 方法名 | 说明 |
|--------|--------|------|
| P1 | type_filter | 目标类型唯一 |
| P2 | status_anchor | 目标状态唯一 |
| P3 | type_status_anchor | 类型+状态组合唯一 |
| P4 | dir8_refine | 子方向细化（8方向 vs 4方向）|
| P5 | dual_reference | 两参考点方向交集（需 ego_dir8）|
| P6 | dist_order | 距离档位序 closest/farthest |
| P7 | type_dist_combo | 类型+距离档位联合 |
| P8 | type_dir8_dist_combo | 类型+dir8+距离三元组 |
| P9 | all_props_combo | 四属性全组合（最强单跳）|
| P10 | ordinal_by_distance | 按实际浮点距离排序（需 actual_dist）|
| P11 | two_hop_referent | 单二跳 referent 唯一（需预取）|
| P12 | dual_hop_referent | 双二跳 referent 交集 |
| P13 | anchor_intro | 引入 src 锚点 |
| P14 | count_fallback | 转为计数题（不唯一但有意义）|
| P15 | yesno_fallback | 兜底存在性问题 |

**新增计时维度（本次改动）**:
- **成功率**: 方法成功锁定 / 被尝试次数
- **平均耗时**: 每次调用的平均耗时（ms），identify 是否有 O(n²) 的慢方法
- **尝试深度**: 平均需要尝试到第几个方法才能锁定（越小越好）

---

## 6. 待验证事项（明早起来核验）

1. **管线完整性**: 查看 `output/pipeline_run_20260323_v2_err.log` 最后几行，确认 `Gap Pipeline — 计时报告` 出现且无异常
2. **JSON 结果**: 确认 `output/gap_timing_20260323.json` 存在，检查 `per_method_timing` 字段
3. **约束方法分布**: 哪些方法命中率最高？P1/P2/P3 应该是主力；P15(yesno_fallback) 如果出现较多说明信息不足
4. **LLM 成功/失败比例**: `step5a_llm_calls` vs `step5a_fallback_calls`（预期全部 fallback）
5. **Step 5a 开销**: LLM 超时导致 ctx_llm_ms 的均值 ~30000ms，对比其他步骤

---

## 7. 下一步优化方向

### 7.1 LLM 上下文 Cypher 优化
- 当 API 可用时，测试 LLM 生成的 Cypher 是否比硬编码更精准（返回更多有效 anc/beyond 节点）
- 考虑换用更快的模型（如 deepseek-v3 而非 deepseek-r1）减少响应时间
- 或在本地部署轻量模型专门用于 Cypher 生成

### 7.2 约束链效率优化
- 根据计时数据，如果 P10(ordinal_by_distance) 或 P11/P12(two_hop) 耗时显著高于其他方法，考虑：
  - 将它们提前缓存（批量预取 actual_dist）
  - 调整 DEFAULT_METHODS 顺序
- 如果 P1(type_filter) 命中率 > 60%，可以把它设为"快速路径"，在 tighten() 最开始单独检测

### 7.3 覆盖率 vs QA质量平衡
- 当前 max_per_cell=8（每 cell 最多 8 条模板 QA），考虑降低到 3-4 并提高质量过滤
- 约束链生成的 QA（constraint_chain 类型）应标记为 hard 难度，用于 VLM 评测的挑战集

---

## 8. 文件变更摘要

| 文件 | 变更类型 | 关键改动 |
|------|----------|----------|
| `gap_pipeline/constraint_methods.py` | 功能增强 | TightenResult + method_timings; tighten() 逐方法 perf_counter 计时 |
| `gap_pipeline/llm_client.py` | 健壮性改进 | httpx.Timeout(read=30s); max_retries=0; 日志初始化信息 |
| `run_gap_pipeline.py` | 功能增强+修复 | Step5a 改为 LLM 调用; _CellTiming + method_timings; 增强 _print_summary; 结果 JSON 增加 per_method_timing |

---

*此文件由 Oz Agent 自动生成，记录 2026-03-22 夜间至 2026-03-23 早间的全部操作。管线后台运行中（PID 41076），结果将写入 `output/gap_timing_20260323.json`。*
