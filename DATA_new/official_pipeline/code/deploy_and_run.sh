#!/bin/bash
# =============================================================================
# ADVTEST VQA Pipeline — 新服务器一键部署 + 运行
#
# 使用前提:
#   1. 目标服务器上已有 DATA_new/data/ (NuScenes 数据集)
#   2. 已从主服务器同步了 official_pipeline/code/ 和 plans/
#   3. Neo4j 已安装并启动
#   4. conda 环境 advtest 已创建
#
# 不需要同步:
#   - filtered_scene_graphs/ — Phase 1 会从 NuScenes 数据自动生成
#   - outputs/ — 每台服务器独立生成
#
# 用法:
#   bash deploy_and_run.sh <plan_file>
#   例: bash deploy_and_run.sh plans/plan_C_remote2.json
#
# 同步命令 (在主服务器执行):
#   rsync -avz --delete --exclude='_archive' --exclude='__pycache__' \
#     official_pipeline/{code,plans,advtest_runtime.env} TARGET:DATA_new/official_pipeline/
# =============================================================================

set -euo pipefail

# ═════════════════════════════════════════════════════════════════
# ★★★ 配置区 — 根据目标服务器修改 ★★★
# ═════════════════════════════════════════════════════════════════

DATA_ROOT="/home/yunyang/ADVTEST/DATA_new"
PIPELINE_DIR="${DATA_ROOT}/official_pipeline"
OUTPUT_DIR="${DATA_ROOT}/outputs"
FILTERED_SG_DIR="${DATA_ROOT}/filtered_scene_graphs"
NEO4J_HOME="/home/yunyang/ADVTEST/neo4j"
PYTHON="/home/yunyang/.conda/envs/advtest/bin/python3"
PLAN_FILE="${1:?用法: bash deploy_and_run.sh <plan_file>  例: plans/plan_C_remote2.json}"

# ═════════════════════════════════════════════════════════════════

cd "${PIPELINE_DIR}"

TOTAL=$(${PYTHON} -c "import json; print(json.load(open('${PLAN_FILE}'))['frame_count'])")

echo "╔════════════════════════════════════════════════════════╗"
echo "║  ADVTEST VQA Pipeline — 部署 + 运行                    ║"
echo "╚═════════════════════════════���══════════════════════════╝"
echo ""
echo "  DATA_ROOT:  ${DATA_ROOT}"
echo "  PLAN:       ${PLAN_FILE} (${TOTAL} 帧)"
echo "  OUTPUT:     ${OUTPUT_DIR}"
echo "  TIME:       $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ═══ Step 1: 环境检查 ═══════════════════════════════════════════
echo "═══ [1/6] 环境检查 ═══"

echo -n "  Python: "; ${PYTHON} --version 2>&1

echo -n "  Neo4j: "
${NEO4J_HOME}/bin/neo4j status 2>/dev/null || {
    echo "  ⚠️  Neo4j 未运行，正在启动..."
    ${NEO4J_HOME}/bin/neo4j start
    sleep 8
}
${PYTHON} -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563'))
with d.session() as s: s.run('RETURN 1')
d.close()
print('  ✅ Neo4j 连接正常')
"

MISSING=0
for f in code/run_batch_fast.py code/run_gap_pipeline_v7.py advtest_runtime.env "${PLAN_FILE}"; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ $f 缺失!"; MISSING=$((MISSING+1)); fi
done

# NuScenes 数据检查
if [ -f "${DATA_ROOT}/data/v1.0-trainval/scene.json" ]; then
    echo "  ✅ NuScenes data"
else
    echo "  ❌ NuScenes data 缺失!"; MISSING=$((MISSING+1))
fi

if [ $MISSING -gt 0 ]; then echo "⛔ ${MISSING} 个必需文件缺失"; exit 1; fi
echo ""

# ═══ Step 2: 创建必需目录 ══════════════════════════════════════
echo "═══ [2/6] 创建目录 ═══"
mkdir -p "${OUTPUT_DIR}"
mkdir -p "${FILTERED_SG_DIR}"
echo "  ✅ ${OUTPUT_DIR}"
echo "  ✅ ${FILTERED_SG_DIR}"
echo ""

# ═══ Step 3: Import 验证 ═══════════════════════════════════════
echo "═══ [3/6] Import 链验证 ═══"
${PYTHON} -c "
import sys; sys.path.insert(0, 'code')
import advtest_env; advtest_env.load_advtest_env()
import advtest_paths as ap
print(f'  ADVTEST_ROOT:    {ap.ADVTEST_ROOT}')
print(f'  FILTERED_SG_DIR: {ap.FILTERED_SG_DIR}')
from run_gap_pipeline_v7 import load_frame_from_plan, V7ArtifactPaths
print('  ✅ All imports OK')
"
echo ""

# ═══ Step 4: Phase 1 — 离线处理 ════════════════════════════════
echo "═══ [4/6] Phase 1: 离线处理 (场景图生成 + 初始覆盖) ═══"
echo "  ${TOTAL} 帧，从 NuScenes 数据生成场景图..."
echo "  开始: $(date '+%H:%M:%S')"
P1_START=$(date +%s)

${PYTHON} code/run_batch_fast.py "${PLAN_FILE}" \
    --phase 1 \
    --output-root "${OUTPUT_DIR}" \
    2>&1 | tee "${OUTPUT_DIR}/phase1_$(date +%Y%m%d_%H%M%S).log"

P1_END=$(date +%s)
P1_ELAPSED=$(( P1_END - P1_START ))
echo ""
echo "  ✅ Phase 1 完成: ${P1_ELAPSED}s ($(( P1_ELAPSED / 60 ))min)"
echo ""

# ═══ Step 5: 冒烟测试 ══════════════════════════════════════════
echo "═══ [5/6] 冒烟测试 (Phase 2, 第1帧) ═══"
${PYTHON} code/run_batch_fast.py "${PLAN_FILE}" \
    --phase 2 \
    --start 0 --end 1 \
    --output-root "${OUTPUT_DIR}" \
    2>&1 | tail -5

FIRST_FRAME=$(${PYTHON} -c "
import json; d=json.load(open('${PLAN_FILE}'))
f=d['frames'][0]; print(f\"{f['scene_id']}_frame{f['frame_id']}\")
")
if [ -f "${OUTPUT_DIR}/${FIRST_FRAME}/generation/qa/${FIRST_FRAME}_round1.csv" ]; then
    echo "  ✅ 冒烟通过"
else
    echo "  ❌ 冒烟失败，请检查日志"; exit 1
fi
echo ""

# ═══ Step 6: Phase 2 — 全量生成 (后台) ═════════════════════════
echo "═══ [6/6] Phase 2: 全量在线生成 (后台) ═══"
LOG_FILE="${OUTPUT_DIR}/batch_v7_$(date +%Y%m%d_%H%M%S).log"

nohup ${PYTHON} code/run_batch_fast.py "${PLAN_FILE}" \
    --phase 2 \
    --output-root "${OUTPUT_DIR}" \
    > "${LOG_FILE}" 2>&1 &

PID=$!
echo "  PID: ${PID}"
echo "  LOG: ${LOG_FILE}"

sleep 15
if kill -0 ${PID} 2>/dev/null; then
    DONE=$(grep -c "GENERATE.*OK\|SKIP" "${LOG_FILE}" 2>/dev/null || echo 0)
    echo "  ✅ 运行中，已完成 ${DONE} 帧"
else
    echo "  ❌ 进程退出"; tail -20 "${LOG_FILE}"; exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  ✅ 部署完成！${TOTAL} 帧正在后台生成                   ║"
echo "╠════════════════════════════════════════════════════════╣"
echo "║  查看进度: tail -f ${LOG_FILE}"
echo "║  统计:     grep 'GENERATE.*OK' ${LOG_FILE} | wc -l"
echo "║  停止:     kill ${PID}"
echo "╚════════════════════════════════════════════════════════╝"
