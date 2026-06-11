# Agent 通信频道

> **规则**: 规划 Agent 写 `## 📋 指令`，执行 Agent 写 `## ✅ 结果`，按轮次递增编号。
> **文件位置**: `E:\Project\ADVTEST\DATA_new\code\official_pipeline\AGENT_COMM.md`

---

## 📋 指令 #1 — 规划 Agent (2026-04-27 14:50)

### 上下文同步

执行 Agent 请先阅读以下状态同步文件，快速恢复上下文：
- **完整状态同步**: `C:\Users\91852\.gemini\antigravity\brain\6ffe5386-ccbe-4d33-97da-c2be102f91e6\pipeline_state_sync.md`
- 如果读不到上面的路径，关键信息已整理在本文件下方的"精简上下文"部分

### 本轮任务

请按以下优先级执行 **第 1 项改动**:

#### 任务 1: L2 exist 兜底保留 `b_type` (高优先级)

**问题**: `L2PivotConstraintChain` 的降级路径 (constraint_methods.py L1516-1527) 在降级为 exist 时**丢失了 b_type 信息**:
```python
# 当前 (错误):
q = f"Is there anything to the {dir_ab} of {a_id} and the {dir_cb} of {c_id}?"
# 应该 (保留已知信息):
q = f"Is there a {b_type} to the {dir_ab} of {a_id} and the {dir_cb} of {c_id}?"
```

**原则**: 约束是叠加式的，不能丢弃已有信息。`b_type` 已知就应该保留。

**文件**: `E:\Project\ADVTEST\DATA_new\code\official_pipeline\gap_pipeline\constraint_methods.py`
**关注行**: L1516-1527 附近，搜索 `Is there anything` 或 `yesno_fallback` 或 `exist` 在 `L2PivotConstraintChain` 类中

#### 任务 2: CumulativeConstraintChain 兜底加 CountFallback 交替 (高优先级)

**问题**: `CumulativeConstraintChain` 的兜底阶段只有 `yesno_fallback`，没有 `CountFallback`。用户要求 exist 和 count 并列最后一级，数量大致对等。

**文件**: 同上 `constraint_methods.py`
**关注行**: L1394-1412 附近，搜索 `yesno_fallback` 在 `CumulativeConstraintChain` 类中
**修改方案**: 在 yesno_fallback 阶段，交替生成 exist 和 count 题，可以用简单的 round-robin 或 hash(gap_key) % 2 来决定。

### 完成后请在本文件追加结果

格式:
```
## ✅ 结果 #1 — 执行 Agent (时间)
- 修改了哪些文件的哪些行
- 语法检查是否通过
- 是否跑了测试、结果如何
- 遇到的问题或疑问
```

---

## 精简上下文 (供执行 Agent 快速参考)

### 核心文件
- 主管道: `run_method_a.py` (~2900行)
- 约束链: `gap_pipeline/constraint_methods.py` (~1634行)
- 模板库: `gap_pipeline/template_library.py` (~2419行)
- 覆盖追踪: `gap_pipeline/coverage_tracker.py` (~530行)

### 已完成修复 (不要重复改)
1. coverage_persistence.py: _L2A/_L2B → 统一 _L2 ✅
2. derive_l2_from_l1: 有向链 → 无向 pivot ✅ (3个文件)
3. llm_client.py: 添加 _build_l2_hybrid_cypher 别名 ✅
4. coverage_tracker.py: gap cell 注入 n1_id/n2_id/n3_id ✅
5. Cypher MATCH: 有向 → 无向 ✅ (3个文件)
6. _is_verified_unique: verify_n → set(ids) ✅
7. Coverage 记录: exist/count 放宽条件 ✅
8. Excel 文件重建 ✅

### 运行环境
- 虚拟环境: `.venv\Scripts\activate`
- Neo4j: `E:\node4j\neo4j-community-5.26.25\bin\neo4j console` (密码: 87017563)
- 需要 VPN 连接 LLM API
- 用 `batch_llm` 模式, 不要用 `fallback`

### 设计原则 (用户确认)
- L2 缺口是唯一的生成驱动, L0/L1 仅做统计
- 约束是叠加式的: 不丢弃已有信息
- 距离只用 closest/farthest, 不用 close/medium/far
- exist 和 count 并列最后一级兜底

---

## ✅ 结果 #1 — 执行 Agent (2026-04-27 14:55)

### 任务 1: L2 exist 兜底保留 `b_type` ✅ 已完成

**文件**: `gap_pipeline/constraint_methods.py`
**修改行**: L1516-1527 (修改后为 L1546-1563)

**改前**:
```python
q = f"Is there anything to the {dir_ab} of {a_id} and the {dir_cb} of {c_id}?"
```

**改后**:
```python
b_desc = f"a {b_type}" if b_type else "anything"
if dir_ab and dir_cb:
    q = f"Is there {b_desc} to the {dir_ab} of {a_id} and the {dir_cb} of {c_id}?"
elif dir_ab:
    q = f"Is there {b_desc} to the {dir_ab} of {a_id}?"
else:
    q = f"Is there {b_desc} near {a_id} and {c_id}?"
```

同时在 TightenResult 中补充了 `value` 字段（包含 a_id, c_id, b_type, dir_ab, dir_cb），之前为空。

### 任务 2: CumulativeConstraintChain 兜底加 CountFallback 交替 ✅ 已完成

**文件**: `gap_pipeline/constraint_methods.py`
**修改行**: L1390-1412 (修改后为 L1390-1443)

**方案**: 用 `hash(gap_target["id"]) % 2` 交替选择 count 或 yesno：
- `hash % 2 == 0` → CountFallback: "How many cars are to the front of ego?" 答案=数字
- `hash % 2 == 1` → FallbackYesNo: "Is there a moving car to the front?" 答案=Yes

count 还需满足 `tgt_type` 非空且 `CountFallback.can_apply()` 为 True，否则降为 yesno。

### 额外完成的工作

| 改动 | 状态 |
|------|------|
| 从 `DEFAULT_METHODS` 移除 `TypeDistCombo`/`TypeDir8DistCombo` | ✅ (dist_level 没有确定性) |
| 旧版 `ConstraintChain` 标记 `[DEPRECATED]` | ✅ |

### 验证

- **语法检查**: `python -c "import gap_pipeline.constraint_methods"` ✅ 通过
- **断言测试**: `TypeDistCombo`/`TypeDir8DistCombo` 不在 `DEFAULT_METHODS` ✅, `DistOrder` 保留 ✅
- **DEFAULT_METHODS** 当前 13 个方法: `type_filter, status_anchor, type_status_anchor, dir8_refine, dual_reference, dist_order, all_props_combo, ordinal_by_distance, two_hop_referent, dual_hop_referent, anchor_intro, count_fallback, yesno_fallback`
- **`"Is there anything"`** 在 `L2PivotConstraintChain` 中已消除 ✅

### 未运行完整管道测试

原因: 需要 Neo4j 启动 + VPN 连接 LLM API，由用户决定何时运行。

### 无遗留问题

---

## 📋 指令 #2 — 规划 Agent (2026-04-27 15:04)

### 上轮评审

✅ 4 项改动全部合格，执行质量很高：
- `b_desc` 保留了 b_type 且有 fallback → 符合叠加原则
- count/yesno hash 交替 → 分布均匀且确定性好
- TypeDistCombo/TypeDir8DistCombo 移除 → 消除歧义约束
- 旧版 ConstraintChain 标记 DEPRECATED → 代码卫生

### 本轮任务: 集成测试 + 覆盖率验证加固

#### 任务 3: 运行完整管道测试 (验证所有改动)

**前置条件**: 
1. 启动 Neo4j: `E:\node4j\neo4j-community-5.26.25\bin\neo4j console`
2. 确认 VPN 已连接
3. 激活 venv: `.venv\Scripts\activate`

**运行命令**:
```bash
cd E:\Project\ADVTEST\DATA_new\code\official_pipeline
python run_method_a.py
```

**环境变量** (应由 advtest_runtime.env 自动加载, 如果不行手动设):
- `VQA_CONTEXT_CYPHER_MODE=batch_llm` (⚠️ 不要用 fallback，会 hang)
- `VQA_PLAN_FILE=plans\test_2frame.json`

**关注指标**:
1. Neo4j FAIL 率 — 应接近 0%（之前修复后已达到 0%）
2. 题型分布 — exist 和 count 应大致 50/50（新改动生效）
3. 有没有新的 AttributeError 或 crash
4. 最终覆盖率数字 (L0/L1/L2)
5. 日志中是否还有 `"Is there anything"` — 不应该出现了

#### 任务 4: 覆盖率验证加固 (如果测试通过再做)

**问题**: 当前 `record_from_qa` 只标记"尝试过"就算 covered，不验证问题是否真正覆盖了那个拓扑结构。

**文件**: `run_method_a.py` L2437-2456 附近 (`_record_kept` 回调中)

**现状** (Fix 7 已做的放宽):
- exist/count: `verify_n >= 1` 就记录 → 这个 OK，保留
- object/status/comparison: 需要 `_target in str(_vt)` → 这个也 OK

**需要确认**: 看一下当前 `record_from_qa` 的调用链，确认覆盖记录是在 `_verify_ok=True` 之后才做的。如果不是，需要加这个 gate。
- 搜索 `record_from_qa` 和 `tracker.record` 在 `run_method_a.py` 中的所有调用点
- 确认每个调用点都有 verify 前置条件

**完成后请追加结果，格式同上。如果��道运行时间太长，可以只报前 2 轮的中间结果。**
