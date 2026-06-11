#!/bin/bash
# =============================================================================
# deploy_v7_quickstart.sh — 上传 v7 文件后一键部署
# 用法: bash deploy_v7_quickstart.sh [plan_file]
# 例如: bash deploy_v7_quickstart.sh plans/plan_B_remote1.json
# =============================================================================

set -e

PIPELINE_DIR="/home/yunyang/ADVTEST/DATA_new/official_pipeline"
cd "$PIPELINE_DIR"

echo "╔════════════════════════════════════════════╗"
echo "║  ADVTEST v7 Pipeline — 服务器 A 快速部署    ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── Step 0: 激活 conda 环境 ──
echo "[0/5] 激活 conda 环境..."
source activate advtest 2>/dev/null || conda activate advtest 2>/dev/null || echo "WARN: conda 激活失败，继续使用当前 Python"
echo "  Python: $(python --version 2>&1)"
echo ""

# ── Step 1: 检查关键文件 ──
echo "[1/5] 检查 v7 必需文件..."
MISSING=0
for f in code/run_gap_pipeline_v7.py run_batch.sh; do
    if [ -f "$f" ]; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f — 缺失!"
        MISSING=$((MISSING + 1))
    fi
done

if [ -d "code/gap_pipeline" ]; then
    COUNT=$(ls code/gap_pipeline/*.py 2>/dev/null | wc -l)
    echo "  ✅ code/gap_pipeline/ ($COUNT 个模块)"
else
    echo "  ❌ code/gap_pipeline/ — 缺失!"
    MISSING=$((MISSING + 1))
fi

if [ -d "plans" ]; then
    echo "  ✅ plans/ ($(ls plans/*.json 2>/dev/null | wc -l) 个计划)"
else
    echo "  ❌ plans/ — 缺失!"
    MISSING=$((MISSING + 1))
fi

SG_COUNT=$(ls /home/yunyang/ADVTEST/DATA_new/filtered_scene_graphs/*.json 2>/dev/null | wc -l)
echo "  场景图: $SG_COUNT 个文件"

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "⛔ $MISSING 个必需文件缺失。请先上传 v7 文件。"
    exit 1
fi
echo ""

# ── Step 2: 配置环境变量 ──
echo "[2/5] 配置环境变量..."
if [ -f "advtest_runtime.env.server_a_ready" ]; then
    cp advtest_runtime.env.server_a_ready advtest_runtime.env
    echo "  ✅ 已使用 server_a_ready 配置"
else
    echo "  ⚠️ 使用现有 advtest_runtime.env"
fi
echo ""

# ── Step 3: 验证 Neo4j ──
echo "[3/5] 验证 Neo4j..."
/home/yunyang/ADVTEST/neo4j/bin/neo4j status 2>/dev/null || {
    echo "  Neo4j 未运行，正在启动..."
    /home/yunyang/ADVTEST/neo4j/bin/neo4j start
    sleep 5
}
python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563'))
with d.session() as s: s.run('RETURN 1')
d.close()
print('  ✅ Neo4j bolt 连接正常')
"
echo ""

# ── Step 4: 冒烟测试 ──
PLAN_FILE="${1:-plans/plan_B_remote1.json}"
echo "[4/5] 冒烟测试 (${PLAN_FILE}, frame 0)..."
echo "  → prepare_scene_graph..."
python code/run_gap_pipeline_v7.py \
    --plan prepare_scene_graph \
    --artifact-root outputs \
    --plan-file "$PLAN_FILE" \
    --frame-index 0 2>&1 | tail -3

echo "  → generate..."
python code/run_gap_pipeline_v7.py \
    --plan generate \
    --artifact-root outputs \
    --plan-file "$PLAN_FILE" \
    --frame-index 0 2>&1 | tail -5
echo ""

# ── Step 5: 就绪! ──
echo "[5/5] ✅ 冒烟测试通过！"
echo ""
echo "现在可以启动全量执行:"
echo "  nohup bash run_batch.sh $PLAN_FILE > batch_stdout.log 2>&1 &"
echo ""
echo "或使用 tmux:"
echo "  tmux new -s advtest"
echo "  bash run_batch.sh $PLAN_FILE"
echo "  # Ctrl+B D 断开"
