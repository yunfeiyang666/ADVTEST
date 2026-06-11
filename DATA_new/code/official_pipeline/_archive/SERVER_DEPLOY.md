# ADVTEST VQA Pipeline — 服务器部署交接

## 一、任务概述

将 VQA 场景图覆盖问答生成 pipeline 部署到服务器上，批量处理约 2200+ 帧的自动驾驶场景数据。Pipeline 从 NuScenes 场景图出发，为每一帧自动生成全覆盖的 VQA 问答对（方向、距离、比较等 5 大类空间推理题型），保证每个三元组 gap (A→B→C) 至少被一道题覆盖。

**你的机器分配的是 `plan_B_remote1.json`（或 `plan_C_remote2.json`），总共 2292（或 2215）帧。**

---

## 二、你会收到的文件

用户会把整个 `official_pipeline/` 文件夹传到你的机器上。预期文件结构如下：

```
official_pipeline/                    ← 工作根目录，cd 到这里操作
├── run_gap_pipeline_v7.py            ← 主入口 (Python)
├── run_batch.sh                      ← 批量执行脚本 (Linux)
├── run_batch_local.ps1               ← 批量执行脚本 (Windows, 本机用)
├── advtest_runtime.env.template      ← 环境变量模板 → 需要你改名+填写
├── advtest_runtime.env               ← (初始是本机路径，需要你改成你的路径)
├── requirements.txt                  ← Python 依赖
│
├── gap_pipeline/                     ← 核心模块（不要修改）
│   ├── __init__.py
│   ├── l2_initial_coverage_analyzer.py
│   ├── l2_constraint_planner.py
│   ├── l2_question_realizer.py
│   ├── template_library.py
│   ├── ... (共 23 个 .py)
│
├── plans/                            ← 批量执行计划
│   ├── plan_A_local.json             ← 本机用 (1504 帧, 不用管)
│   ├── plan_B_remote1.json           ← 远程机1 (2292 帧, scene-0274 ~ scene-0796)
│   ├── plan_C_remote2.json           ← 远程机2 (2215 帧, scene-0797 ~ scene-1073)
│   └── README.md
│
├── advtest_env.py                    ← env 加载辅助
├── advtest_paths.py                  ← 路径解析
├── config.py                         ← 配置
├── core_universe_filter.py           ← 场景图过滤
├── import_single_scene_to_neo4j.py   ← Neo4j 导入
└── ... (其他辅助文件)
```

### 外部数据文件（用户会一起传的）

```
<数据根目录>/
├── data/
│   ├── NuScenes_val_questions.json        ← 原始 NuScenesQA 题库 (83337题)
│   └── test6019_bundle/
│       └── sample_token_to_scene.json     �� sample_token 到 scene 的映射
│
└── filtered_scene_graphs/                 ← 预计算的场景图（每帧一个 JSON）
    ├── scene-0274_frame0_scene_graph.json
    ├── scene-0274_frame1_scene_graph.json
    └── ...
```

---

## 三、你需要做的

### 步骤 1：安装依赖

```bash
cd official_pipeline
pip install -r requirements.txt
# 核心依赖: neo4j>=5.0, openpyxl>=3.1, openai>=1.0, httpx>=0.25
```

### 步骤 2：安装并启动 Neo4j

Pipeline 需要一个本地 Neo4j 实例做空间约束验证。

```bash
# 方式1: Docker (推荐)
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/87017563 \
  neo4j:5-community

# 方式2: 下载社区版
# https://neo4j.com/download/ → neo4j-community-5.x
# bin/neo4j console
```

验证 Neo4j 运行：
```bash
curl -s http://localhost:7474 | head -5
# 应返回 JSON
```

### 步骤 3：配置环境变量

把 `advtest_runtime.env.template` 改名为 `advtest_runtime.env`（或直接修改已有的 `advtest_runtime.env`），填入你机器的实际路径：

```bash
# ═══ 必填项 ═══
ADVTEST_ROOT=/path/to/data_root                                    # 数据根目录
VQA_QA_JSON=/path/to/data/NuScenes_val_questions.json              # 原始题库
ADVTEST_ORIGINAL_QA=/path/to/data/NuScenes_val_questions.json      # 同上
ADVTEST_SAMPLE_TOKEN_MAP=/path/to/data/test6019_bundle/sample_token_to_scene.json
FILTERED_SG_DIR=/path/to/filtered_scene_graphs                    # 场景图目录

# ═══ LLM API（初始覆盖阶段的 fallback 用，generate 阶段不需要）═══
VQA_API_BASE_URL=http://218.197.140.7:3001/v1
VQA_API_KEY=sk-kr0lAPleCoSfE8E40298E9F940C04603B4F17905De08Bd7d
VQA_MODEL_NAME=Qwen3.5-35B-A3B

# ═══ Neo4j（和上面启动的一致）═══
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=87017563
```

> **关键说明**: `run_gap_pipeline_v7.py` 启动时会自动读取同目录下的 `advtest_runtime.env`，不需要你手动 source/export。

### 步骤 4：冒烟测试

先跑 1 帧验证环境是否正常：

```bash
# 只跑离线阶段（不需要 LLM、不需要 VPN）
python run_gap_pipeline_v7.py \
  --plan prepare_scene_graph \
  --artifact-root outputs \
  --plan-file plans/plan_B_remote1.json \
  --frame-index 0

# 如果成功，跑生成阶段（需要 Neo4j）
python run_gap_pipeline_v7.py \
  --plan generate \
  --artifact-root outputs \
  --plan-file plans/plan_B_remote1.json \
  --frame-index 0
```

成功标志：
```
[v7][offline] postprocess_coverage DONE {'records': ..., 'coverage_rate_l2': 1.0, ...}
```

### 步骤 5：全量执行

```bash
# 后台运行，断开 SSH 不中断
nohup bash run_batch.sh plans/plan_B_remote1.json > batch_stdout.log 2>&1 &

# 或用 tmux/screen
tmux new -s advtest
bash run_batch.sh plans/plan_B_remote1.json
# Ctrl+B D 断开
```

---

## 四、执行流程说明

`run_batch.sh` 自动分两阶段执行：

### Phase 1: OFFLINE（所有帧的离线处理）
对 plan 中的每一帧依次执行：
1. `prepare_scene_graph` — 从 `filtered_scene_graphs/` 读取场景图，过滤节点/边，输出标准化 JSON
2. `prepare_initial_coverage` — 解析原始 NuScenesQA 题库，确定性匹配已有覆盖

**不需要 LLM API**，不需要 VPN。纯本地计算，非常快（每帧 < 1 秒）。

### Phase 2: GENERATE（所有帧的问题生成）
对 plan 中的每一帧依次执行：
1. 导入场景图到 Neo4j
2. 构建 gap plan cache（所有 A→B→C 三元组 × 模板匹配）
3. 线性扫描选题 + Neo4j 约束验证
4. 输出覆盖率 100% 的 QA CSV

**需要 Neo4j 运行**，不需要 LLM API。每帧耗时取决于节点数：
- 10-15 节点：~10 秒
- 20-25 节点：~60-90 秒
- 30+ 节点：~5-7 分钟

预计总耗时：**2000 帧 × 平均 60 秒 ≈ 33 小时**。

---

## 五、输出结构

执行完成后，`outputs/` ��每帧一个目录：

```
outputs/
├── scene-0274_frame0/
│   ├── manifest.json                              ← 帧元数据
│   ├── plan_status.json                           ← 执行状态
│   ├── offline/
│   │   ├── scene_graphs/
│   │   │   └── scene-0274_frame0_filtered_scene_graph.json
│   │   └── initial_coverage/
│   │       ├── scene-0274_frame0_initial_coverage.jsonl
│   │       └── scene-0274_frame0_initial_coverage.csv
│   ├── generation/
│   │   ├── qa/
│   │   │   ├── scene-0274_frame0_generated.csv      ← ★ 最终 QA 输出
│   │   │   ├── scene-0274_frame0_generated.jsonl
│   │   │   └── scene-0274_frame0_generated_meta.csv
│   │   └── coverage_state/
│   │       └── scene-0274_frame0_coverage_state.json
│   └── reports/
│       ├── scene-0274_frame0_summary.json           ← 帧级统计
│       └── ...
├── scene-0274_frame1/
│   └── ...
├── batch_20260510_143000.log                        ← 批量执行日志
└── errors.log                                       ← 错误记录（如有）
```

**最终产物是 `generation/qa/*_generated.csv`**，每帧一个，包含所有生成的 VQA 问答���。

---

## 六、故障处理

### 某帧失败
脚本会记录错误并**自动跳过**继续下一帧。查看 `outputs/errors.log` 了解哪些帧失败了。

### 断点续跑
如果中途中断，打开 `batch_*.log` 找到最后成功的帧编号 N，修改 `run_batch.sh` 中的循环起点：
```bash
# 原来
for i in $(seq 0 $((TOTAL - 1))); do
# 改为
for i in $(seq N $((TOTAL - 1))); do
```

### Neo4j 挂了
```bash
# Docker
docker restart neo4j
# 或社区版
bin/neo4j console
```

### 磁盘空间
每帧输出约 1-5MB。2000 帧 ≈ 5-10GB。确保 `outputs/` 所在分区有足够空间。

---

## 七、验证结果

跑完后快速检查：
```bash
# 统计成功帧数
ls outputs/*/generation/qa/*_generated.csv | wc -l
# 应 ≈ 2292 (或 2215)

# 抽查覆盖率
python -c "
import json, glob
for f in sorted(glob.glob('outputs/*/reports/*_summary.json'))[:5]:
    d = json.load(open(f))
    print(f'{d.get(\"scene_id\",\"?\")}_frame{d.get(\"frame_id\",\"?\")}: L2={d.get(\"coverage_rate_l2\",0):.0%} Q={d.get(\"total_generated\",0)}')
"
```

所有帧的 `coverage_rate_l2` 应为 **1.0 (100%)**。
