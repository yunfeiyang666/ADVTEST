# ADVTEST VQA Pipeline — 多服务器部署交接文档

> 最后更新: 2026-05-11

---

## 一、目录结构

```
DATA_new/
├── data/                          # NuScenes 数据集 (13GB)
│   ├── v1.0-trainval/             #   13 个元数据 JSON
│   ├── maps/
│   ├── samples/
│   ├── NuScenes_val_questions.json
│   └── test6019_bundle/
│
├── filtered_scene_graphs/         # 预生成场景图 (1.1GB, 2296 个 JSON)
│
├── outputs/                       # 生成输出 (每台服务器独立)
│   └── scene-XXXX_frameYY/
│
└── official_pipeline/             # 代码 + 配置
    ├── advtest_runtime.env        #   环境变量 (每台服务器不同!)
    ├── plans/                     #   批处理计划 JSON
    │   └── plan_B_remote1.json    #   2292 帧
    ├── code/                      #   全部 Python 代码 (532KB)
    │   ├── run_batch_fast.py      #     批量执行入口
    │   ├── run_gap_pipeline_v7.py #     核心 pipeline
    │   ├── advtest_env.py
    │   ├── advtest_paths.py
    │   ├── config.py
    │   ├── import_scene_graph_http.py
    │   ├── import_single_scene_to_neo4j.py
    │   ├── run_batch.sh
    │   ├── requirements.txt
    │   └── gap_pipeline/          #     22 个核心模块
    └── _archive/                  #   废弃文件 (不需要同步)
```

---

## 二、核心代码

所有运行时代码在 `official_pipeline/code/` 下，**总共 532KB**。

| 文件 | 功能 |
|------|------|
| `run_batch_fast.py` | 批量执行入口，断点续传 |
| `run_gap_pipeline_v7.py` | 核心 pipeline (2355 行) |
| `advtest_env.py` | 环境变量加载 |
| `advtest_paths.py` | 统一路径解析 |
| `config.py` | S3C 实验参数 |
| `gap_pipeline/` | 22 个核心模块 (选题/规划/验证/生成/模板) |

---

## 三、同步到新服务器

```bash
TARGET=user@new_server

# 1. 创建目录
ssh $TARGET "mkdir -p /home/yunyang/ADVTEST/DATA_new/official_pipeline"

# 2. 同步代码 (532KB)
rsync -avz --delete \
  official_pipeline/code/ \
  $TARGET:/home/yunyang/ADVTEST/DATA_new/official_pipeline/code/

# 3. 同步计划
rsync -avz --delete \
  official_pipeline/plans/ \
  $TARGET:/home/yunyang/ADVTEST/DATA_new/official_pipeline/plans/

# 4. 同步场景图 (1.1GB, 首次较慢)
rsync -avz --delete \
  filtered_scene_graphs/ \
  $TARGET:/home/yunyang/ADVTEST/DATA_new/filtered_scene_graphs/

# 5. 不要同步: outputs/ (每台独立), advtest_runtime.env (需手动配), _archive/
```

---

## 四、环境变量 (`advtest_runtime.env`)

在目标服务器 `official_pipeline/advtest_runtime.env` 中配置：

```bash
# ──── 路径 (★ 改成目标服务器实际路径) ────
ADVTEST_ROOT=/home/yunyang/ADVTEST/DATA_new
NUSCENES_DATAROOT=/home/yunyang/ADVTEST/DATA_new/data
NUSCENES_VERSION=v1.0-trainval
VQA_QA_JSON=/home/yunyang/ADVTEST/DATA_new/data/NuScenes_val_questions.json
ADVTEST_ORIGINAL_QA=/home/yunyang/ADVTEST/DATA_new/data/NuScenes_val_questions.json
ADVTEST_SAMPLE_TOKEN_MAP=/home/yunyang/ADVTEST/DATA_new/data/test6019_bundle/sample_token_to_scene.json
FILTERED_SG_DIR=/home/yunyang/ADVTEST/DATA_new/filtered_scene_graphs

# ──── LLM API (所有服务器相同) ────
VQA_API_BASE_URL=http://218.197.140.7:3001/v1
VQA_API_KEY=sk-kr0lAPleCoSfE8E40298E9F940C04603B4F17905De08Bd7d
VQA_MODEL_NAME=Qwen3.5-35B-A3B
VQA_TIMEOUT_SECONDS=300

# ──── Neo4j (★ 端口按实际改) ────
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=87017563
```

**需要改的**: `ADVTEST_ROOT` 系列路径、`NEO4J_URI`  
**不需要改的**: LLM API 配置、运行参数

---

## 五、依赖安装

```bash
conda create -n advtest python=3.11 -y && conda activate advtest
pip install neo4j>=5.0 openpyxl>=3.1 openai>=1.0 httpx>=0.25 \
  pyquaternion>=0.9.9 pandas numpy tqdm nuscenes-devkit

# Neo4j: 安装到 /home/yunyang/ADVTEST/neo4j/
# 设密码: neo4j/bin/neo4j-admin dbms set-initial-password 87017563
# 启动:   neo4j/bin/neo4j start
```

---

## 六、启动

```bash
cd /home/yunyang/ADVTEST/DATA_new/official_pipeline

# 冒烟测试 (1 帧)
python3 code/run_batch_fast.py plans/plan_B_remote1.json --start 0 --end 1

# 全量 (后台)
nohup python3 code/run_batch_fast.py plans/plan_B_remote1.json \
  > ../outputs/batch_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# 多服务器分片
# Server A: --start 0 --end 764
# Server B: --start 764 --end 1528
# Server C: --start 1528 --end 2292
```

---

## 七、输出说明

每帧生成:
- `*_round1.csv/jsonl` — Round 1 覆盖类 (converge + diverge)
- `*_round2.csv/jsonl` — Round 2 均衡题型 (chain + viewpoint, Round-Robin)
- `*_all.csv/jsonl` — 合并题库
