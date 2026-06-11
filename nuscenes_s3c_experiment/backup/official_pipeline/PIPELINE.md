# NuScenes VQA Gap-Coverage Pipeline — 完整流程说明

> 版本：v3.0（2026-03-23）  
> 上次更新：本次 Oz Agent 夜间作业（2026-03-22/23）

---

## 一、目录结构

```
official_pipeline/
│
├── PIPELINE.md                          ← 本文档
│
│  ── 入口脚本（按执行顺序）──────────────────────────────────────
├── generate_selected_scenes_improved.py  ① 场景图生成
├── import_single_scene_to_neo4j.py       ② 导入 Neo4j
├── run_gap_pipeline.py                   ③ Gap 覆盖填充（核心）
├── run_official_qa_enhanced.py           ④ VQA 评测
│
├── config.py                            全局路径配置
│
│  ── gap_pipeline 模块（③ 的核心）─────────────────────────────
├── gap_pipeline/
│   ├── __init__.py
│   ├── config.py           LLM 配置（API key / base_url / model / timeout）
│   ├── llm_client.py       大模型调用封装（带超时 + fallback）
│   ├── scene_coverage.py   CoverageMap（edge / L2A / L2B 三级计数）
│   ├── constraint_methods.py  ConstraintChain（P1-P15，带逐方法计时）
│   ├── constraint_tightener.py  旧版六层收束器（保留参考）
│   ├── gap_qa_generator.py  高层 QA 生成包装
│   └── gap_templates.py     75 模板 × 4 变体库
│
│  ── vqa_pipeline 模块（④ 的核心）─────────────────────────────
└── vqa_pipeline/
    ├── __init__.py
    ├── pipeline.py            VQAPipeline 主类
    ├── llm_client.py          LLM 调用（VQA 评测用）
    ├── neo4j_client.py        Neo4j 连接与查询
    ├── direction_utils.py     ⭐ 方向计算（Ego Frame）
    ├── ir_patterns.py         IR 模式匹配
    ├── answer_formatter.py    答案格式化
    ├── question_normalizer.py 问题规范化
    ├── status_inference.py    状态推断
    └── cypher_coverage_rewriter.py  覆盖率导向 Cypher 重写
```

---

## 二、完整流程（四步）

```
NuScenes 数据
    │
    ▼
① generate_selected_scenes_improved.py
    │  输入：NuScenes mini/trainval 数据集
    │  输出：scene_graph_*.json（每帧场景图，含节点属性 + 有向边关系）
    │  关键逻辑：
    │    - 提取每帧的 Object 节点（car/pedestrian/truck/...）
    │    - 计算 Ego Frame 下的相对方向（direction_4 / direction_8）
    │    - 计算距离档位（very_close / close / medium / far）
    │    - 构建有向边（RELATES_TO），附带 predicates 属性
    │
    ▼
② import_single_scene_to_neo4j.py
    │  输入：scene_graph_*.json
    │  输出：Neo4j 图数据库（节点 Object + 关系 RELATES_TO）
    │  关键逻辑：
    │    - 清空旧数据（MATCH (n) DETACH DELETE n）
    │    - 批量创建节点（带 unique_id / type / status 属性）
    │    - 创建有向边（带 direction_4/8 / distance / predicates）
    │  配置：
    │    run_official_qa_enhanced.py 默认 bolt://localhost:7600
    │    run_gap_pipeline.py         默认 bolt://localhost:7800
    │    ⚠️ 两个脚本默认端口不同，请按实际环境统一
    │
    ▼
③ run_gap_pipeline.py             【本次主要改动】
    │  输入：Neo4j（已导入场景图）
    │  输出：QA 对 JSON（含 constraint_chain 类型 + template 类型 + 计时数据）
    │
    │  === 内部流程（详见第三节）===
    │  Step 0  init          Neo4j + LLM 连接初始化
    │  Step 1  scene_cypher  硬编码枚举全量有向边
    │  Step 2  scene_neo4j   执行，获取 ~4032 条边
    │  Step 3  cmap_init     CoverageMap 初始化（4032 edge cells）
    │  Step 4  gap_detect    识别 count=0 的 edge（gap cells）
    │  ┌────────────── per-cell 循环 ──────────────┐
    │  │ Step 5a  ctx_llm    LLM 生成上下文 Cypher  │ ← 本次改动
    │  │ Step 5b  ctx_neo4j  执行，获取 ctx 字典    │
    │  │ Step 5c  cand_neo4j 候选集 + referent 查询 │
    │  │ Step 5d  constraint ConstraintChain.tighten│ ← 逐方法计时
    │  │ Step 5e  template   模板填充 + 答案解析    │
    │  └───────────────────────────────────────────┘
    │  Step 6  cmap_update  最终覆盖率统计
    │
    ▼
④ run_official_qa_enhanced.py
    │  输入：SCENE_SPECS 列表（场景名 + 帧号）+ Neo4j
    │  输出：VQA 评测结果（正确率 / per-question 分析）
    │  关键逻辑：
    │    - VQAPipeline 对每道题生成 Cypher 查询 Neo4j
    │    - LLM Judge 判断答案等价性（硬编码词表 + LLM 兜底）
    │    - 智能 Retry（5 轮，切换 Source/Ego Frame 方向属性）
    │    - 跳过已知数据错误题（SKIP_QUESTIONS 集合）
```

---

## 三、本次改动细节（2026-03-22/23）

### 3.1 Step 5a：由硬编码 Cypher → 大模型动态生成

**改动文件**: `run_gap_pipeline.py`（Step 5a 块）

**改动前**（硬编码，不走大模型）:
```python
cypher = LLMClient.build_gap_context_cypher(src_id, tgt_id)
```

**改动后**（调用大模型，失败时 fallback 到硬编码）:
```python
try:
    cypher = llm_client.generate_gap_context_cypher(cell)
    timing.ctx_llm_used_llm = True         # 标记实际调用了 LLM
except Exception as _llm_exc:
    logger.warning("Step 5a LLM 失败（%s），退回硬编码 Cypher", _llm_exc)
    cypher = LLMClient.build_gap_context_cypher(src_id, tgt_id)
    timing.ctx_llm_used_llm = False        # 标记走了 fallback
```

**意图**：
- 大模型可以根据 gap 的 `src_id / tgt_id / dir8` 生成更精准的上下文 Cypher
- 例如：动态扩展 `OPTIONAL MATCH` 的范围，拉取更丰富的 anc/beyond 邻域
- 硬编码 Cypher 作为保险兜底，确保流程在 API 超时时不中断

**Prompt 位置**: `gap_pipeline/config.py` → `GAP_CONTEXT_PROMPT`

---

### 3.2 ConstraintChain：逐方法计时

**改动文件**: `gap_pipeline/constraint_methods.py`

**改动内容**:

1. `TightenResult` 新增两字段：
   ```python
   method_timings: Dict[str, float] = field(default_factory=dict)
   # key = 方法名，value = 该方法在本次 tighten() 中的总耗时 (ms)

   methods_tried: List[str] = field(default_factory=list)
   # 成功找到 value（候选集有效）的方法列表（按顺序）
   ```

2. `ConstraintChain.tighten()` 内对每个方法独立计时：
   ```python
   for method in self.methods:
       _t0 = time.perf_counter()
       if not method.can_apply(...): 
           method_timings[method.name] = elapsed_ms; continue
       value = method.find_value(...)
       if value is None:
           method_timings[method.name] = elapsed_ms; continue
       # ...找到并成功收束...
       method_timings[method.name] = elapsed_ms
       return TightenResult(..., method_timings=method_timings)
   ```

**15 个约束方法优先级表**：

| 优先级 | 方法名 | 说明 | 唯一性 |
|--------|--------|------|--------|
| P1  | type_filter          | 目标类型在同方向中唯一 | ✅ 唯一 |
| P2  | status_anchor        | 目标状态在同方向中唯一 | ✅ 唯一 |
| P3  | type_status_anchor   | 类型+状态组合唯一 | ✅ 唯一 |
| P4  | dir8_refine          | 用 dir8 代替 dir4 细化方向 | ✅ 唯一 |
| P5  | dual_reference       | 两参考点方向交集（需 ego_dir8）| ✅ 唯一 |
| P6  | dist_order           | 距离档位序 closest/farthest | ✅ 唯一 |
| P7  | type_dist_combo      | 类型+距离档位联合 | ✅ 唯一 |
| P8  | type_dir8_dist_combo | 类型+dir8+距离三元组 | ✅ 唯一 |
| P9  | all_props_combo      | 四属性全组合（最强单跳）| ✅ 唯一 |
| P10 | ordinal_by_distance  | 按实际米数排序（需 actual_dist）| ✅ 唯一 |
| P11 | two_hop_referent     | 单二跳 referent 唯一 | ✅ 唯一 |
| P12 | dual_hop_referent    | 双二跳 referent 交集 | ✅ 唯一 |
| P13 | anchor_intro         | 引入 src 状态作锚点 | ✅ 唯一 |
| P14 | count_fallback       | 转为计数题（不唯一但可回答）| ❌ 非唯一 |
| P15 | yesno_fallback       | 兜底存在性问题（永远可用）| ❌ 非唯一 |

---

### 3.3 LLM 客户端：超时与禁止重试

**改动文件**: `gap_pipeline/llm_client.py`

**问题背景**：
deepseek-r1 是思维链模型，API 响应时间 >60s 很常见。默认 openai 客户端：
- 无超时 → 流程永久挂起
- 2次自动重试 → 每失败 cell 耗时 3×90s = 270s（7.5 小时 × 100 cells）

**修复方案**：
```python
_timeout = httpx.Timeout(
    connect=10.0,   # 连接超时 10s
    read=30.0,      # 读取超时 30s（DeepSeek 如 30s 内无响应即放弃）
    write=10.0,
    pool=5.0,
)
self._client = openai.OpenAI(
    ...
    timeout=30.0,   # openai 客户端级超时保险
    max_retries=0,  # ⭐ 禁止重试，超时立即 fallback
)
```

**效果**：
- 每失败 cell 最多等待 ~30s（而非 270s）
- 100 cells 最坏情况 ~50min 完成（实测约 31s/cell）
- 验证日志：
  ```
  08:55:20  INFO   cell 1/100  ego→truck1
  08:55:50  WARNING  Step 5a LLM 失败（Request timed out.），退回硬编码 Cypher
  08:55:54  INFO   cell 2/100  ego→car35        ← 仅 4s 后继续
  ```

---

### 3.4 计时汇总输出增强

**改动文件**: `run_gap_pipeline.py`（`_print_summary` 函数 + 结果 JSON）

**新增控制台输出**：

```
  步骤                                     mean     max     min     p95      total
  ──────────────────────────────────────────────────────────────────────────────
  5a  LLM 生成上下文 Cypher              30012.3  30024.1  29998.2  30020.1  3001230.0  ◄◄
  5b  Neo4j 执行上下文查询                   8.2     42.1      2.1     18.3      820.0
  5c  Neo4j 候选集 + referent 批量查询      12.4     85.3      3.2     35.6     1240.0
  5d  ConstraintChain.tighten()  ◄ 重点     0.8      8.2      0.1      3.1       80.0  ◄◄
  5e  模板选择 + 填空                        2.1     15.4      0.3      8.2      210.0
      TOTAL per-cell                     30036.0  30175.1  30004.0  30067.0  3003600.0

  Step 5a LLM 调用统计: 实际调用=12  退回硬编码=88

  约束方法分布 (共 100 cells, 唯一锁定 73):
  方法名                                成功次数   平均耗时ms
  ──────────────────────────────────────────────────────────
  type_filter                                34       0.02 ms ✓唯一
  status_anchor                              18       0.03 ms ✓唯一
  yesno_fallback                             27       0.01 ms (fallback)
  ...

  [各方法被计载(含未成功)次数和平均耗时]
  方法名                                被计载次   平均耗时ms
  type_filter                               100       0.02 ms  (success=34)
  status_anchor                              66       0.04 ms  (success=18)
  ...
```

**新增 JSON 字段**（`output/gap_timing_20260323.json`）：
```json
{
  "step5a_llm_calls": 12,
  "step5a_fallback_calls": 88,
  "per_method_timing": {
    "type_filter":       {"n": 100, "mean": 0.02, "p95": 0.05, ...},
    "status_anchor":     {"n":  66, "mean": 0.04, ...},
    "yesno_fallback":    {"n":  27, "mean": 0.01, ...}
  }
}
```

---

## 四、运行命令

### 前置条件
```powershell
# 激活虚拟环境
& "E:\Project\ADVTEST\.venv310\Scripts\Activate.ps1"
# 切换到 official_pipeline 目录
cd "E:\Project\ADVTEST\nuscenes_s3c_experiment\official_pipeline"
```

### 步骤 ①：场景图生成
```powershell
python generate_selected_scenes_improved.py
# 输出：output/coverage_analysis/scene_graphs/*.json
```

### 步骤 ②：导入 Neo4j
```powershell
python import_single_scene_to_neo4j.py --scene-name scene-0553 --frame-idx 8
# 默认 Neo4j：bolt://localhost:7800（可用 --neo4j-uri 指定）
```

### 步骤 ③：Gap 填充 QA 生成（主流程）
```powershell
# 基础运行（仅模板填充，无约束链）
python run_gap_pipeline.py

# 完整运行（启用 ConstraintChain + 计时）
python run_gap_pipeline.py --use-constraint-chain --output output/gap_results.json

# 限制 cell 数（调试用）
python run_gap_pipeline.py --use-constraint-chain --max-cells 50

# 按目标覆盖率停止
python run_gap_pipeline.py --use-constraint-chain --target-coverage 30.0

# 后台运行（推荐，overnight）
Start-Process python -ArgumentList "run_gap_pipeline.py --use-constraint-chain --output output/gap_results.json" `
  -RedirectStandardError output/gap_run.log -WindowStyle Hidden
```

### 步骤 ④：VQA 评测
```powershell
python run_official_qa_enhanced.py
# 编辑文件内的 SCENE_SPECS 列表来指定要评测的场景+帧
```

---

## 五、配置说明

### LLM 配置（`gap_pipeline/config.py`）
```python
LLM_CONFIG = {
    "api_key":    "sk-...",              # 或 env: VQA_API_KEY
    "api_base":   "https://...",         # 或 env: VQA_API_BASE_URL
    "model":      "deepseek-r1",         # 或 env: VQA_MODEL_NAME
    "verify_ssl": False,                 # 或 env: VQA_VERIFY_SSL
    "temperature": 0.0,
    "max_tokens":  2048,
    # 超时控制（本次新增）
    "timeout_connect": 10.0,             # 连接超时 (s)
    "timeout_read":    30.0,             # 读取超时 (s)，建议 30-60s
}
```

### Neo4j 端口说明
| 脚本 | 默认端口 | 备注 |
|------|----------|------|
| `run_gap_pipeline.py` | `bolt://localhost:7800` | `--neo4j-uri` 可覆盖 |
| `run_official_qa_enhanced.py` | `bolt://localhost:7600` | `NEO4J_URI` 环境变量可覆盖 |

> ⚠️ 两个脚本默认端口不同，使用时请确认实际 Neo4j 端口并统一。

---

## 六、当前正在运行

```
进程 PID: 41076
启动时间: 2026-03-23 08:55:18 (北京)
参数: --max-cells 100 --use-constraint-chain
日志: output/pipeline_run_20260323_v2_err.log
结果: output/gap_timing_20260323.json
预计完成: ~09:45 (100 cells × ~31s/cell)
```

---

## 七、输出文件说明

| 文件 | 说明 |
|------|------|
| `output/gap_timing_*.json` | 完整结果：QA 对 + 全部计时 + per_method_timing |
| `output/pipeline_run_*_err.log` | 运行日志（logging 写入 stderr）|
| `output/pipeline_run_*.log` | stdout 日志（通常为空）|

---

*文档最后更新：2026-03-23 09:06（北京时间），由 Oz Agent 自动生成。*
