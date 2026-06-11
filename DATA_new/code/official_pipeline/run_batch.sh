#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# ADVTEST VQA Pipeline — 两阶段批量执行脚本 (Linux)
# 用法: bash run_batch.sh <plan_file>
# 示例: bash run_batch.sh plans/plan_B_remote1.json
#
# 阶段1: 对 plan 中所有帧执行离线处理 (prepare_scene_graph + prepare_initial_coverage)
# 阶段2: 对 plan 中所有帧执行在线生成 (generate)
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ═══════════════ 配置区 (每台机器修改) ═══════════════════════

# [必填] official_pipeline 根路径
PIPELINE_ROOT="/home/yunyang/ADVTEST/DATA_new/official_pipeline"

# [必填] 输出根目录
OUTPUT_ROOT="$(dirname "${PIPELINE_ROOT}")/outputs"

# [可选] 并发数
CONCURRENCY=4

# ═══════════════ 不需要改的部分 ════════════════════════════

PLAN_FILE="${1:?Usage: bash run_batch.sh <plan_file>}"

cd "${PIPELINE_ROOT}"

# 自动从 advtest_runtime.env 加载 (脚本内部已有 _load_env_file)
# 但为防止 env 没加载到 shell, 也手动 export 一下
if [ -f "advtest_runtime.env" ]; then
    set -a
    source <(grep -v '^\s*#' advtest_runtime.env | grep '=')
    set +a
fi

# 获取帧数
TOTAL=$(python3 -c "import json; d=json.load(open('${PLAN_FILE}', encoding='utf-8')); print(d.get('frame_count', len(d.get('frames',[]))))")

echo "══════════════════════════════════════════════════"
echo " ADVTEST VQA Pipeline — 两阶段批量执行"
echo " Plan:   ${PLAN_FILE}"
echo " Frames: ${TOTAL}"
echo " Output: ${OUTPUT_ROOT}"
echo " Time:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════��═══════"

mkdir -p "${OUTPUT_ROOT}"
LOG_FILE="${OUTPUT_ROOT}/batch_$(date +%Y%m%d_%H%M%S).log"

# ═══════════════ 阶段1: 离线处理 ═══════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  PHASE 1: OFFLINE (scene_graph + initial_cov)   ║"
echo "╚══════════════════════════════════════════════════╝"

OFFLINE_OK=0
OFFLINE_FAIL=0
PHASE1_START=$(date +%s)

for i in $(seq 0 $((TOTAL - 1))); do
    FRAME_INFO=$(python3 -c "
import json
d=json.load(open('${PLAN_FILE}', encoding='utf-8'))
f=d['frames'][${i}]
print(f\"{f['scene_id']}_frame{f['frame_id']}\")
")
    echo "[$(date +%H:%M:%S)] OFFLINE $((i+1))/${TOTAL}: ${FRAME_INFO}" | tee -a "${LOG_FILE}"

    if python3 code/run_gap_pipeline_v7.py \
        --plan prepare_scene_graph \
        --artifact-root "${OUTPUT_ROOT}" \
        --plan-file "${PLAN_FILE}" \
        --frame-index "${i}" \
        2>&1 | tee -a "${LOG_FILE}"; then

        python3 code/run_gap_pipeline_v7.py \
            --plan prepare_initial_coverage \
            --artifact-root "${OUTPUT_ROOT}" \
            --plan-file "${PLAN_FILE}" \
            --frame-index "${i}" \
            --concurrency "${CONCURRENCY}" \
            2>&1 | tee -a "${LOG_FILE}"

        OFFLINE_OK=$((OFFLINE_OK + 1))
    else
        echo "[ERROR] OFFLINE ${FRAME_INFO} FAILED" | tee -a "${LOG_FILE}" "${OUTPUT_ROOT}/errors.log"
        OFFLINE_FAIL=$((OFFLINE_FAIL + 1))
    fi
done

PHASE1_END=$(date +%s)
PHASE1_ELAPSED=$(( PHASE1_END - PHASE1_START ))
echo ""
echo "── Phase 1 DONE: OK=${OFFLINE_OK} FAIL=${OFFLINE_FAIL} Time=${PHASE1_ELAPSED}s ──" | tee -a "${LOG_FILE}"

# ═══════════════ 阶段2: 在线生成 ═══════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  PHASE 2: GENERATE (gap coverage questions)     ║"
echo "╚══════════════════════════════════════════════════╝"

GEN_OK=0
GEN_FAIL=0
PHASE2_START=$(date +%s)

for i in $(seq 0 $((TOTAL - 1))); do
    FRAME_INFO=$(python3 -c "
import json
d=json.load(open('${PLAN_FILE}', encoding='utf-8'))
f=d['frames'][${i}]
print(f\"{f['scene_id']}_frame{f['frame_id']}\")
")
    ELAPSED_S=$(( $(date +%s) - PHASE2_START ))
    if [ $i -gt 0 ]; then
        RATE=$(echo "scale=1; ${ELAPSED_S} / ${i}" | bc 2>/dev/null || echo "?")
        ETA=$(echo "scale=0; (${TOTAL} - ${i}) * ${ELAPSED_S} / ${i} / 60" | bc 2>/dev/null || echo "?")
    else
        RATE="?"
        ETA="?"
    fi
    echo "[$(date +%H:%M:%S)] GENERATE $((i+1))/${TOTAL}: ${FRAME_INFO} (${RATE}s/frame, ETA ~${ETA}min)" | tee -a "${LOG_FILE}"

    if python3 code/run_gap_pipeline_v7.py \
        --plan generate \
        --artifact-root "${OUTPUT_ROOT}" \
        --plan-file "${PLAN_FILE}" \
        --frame-index "${i}" \
        2>&1 | tee -a "${LOG_FILE}"; then
        GEN_OK=$((GEN_OK + 1))
    else
        echo "[ERROR] GENERATE ${FRAME_INFO} FAILED" | tee -a "${LOG_FILE}" "${OUTPUT_ROOT}/errors.log"
        GEN_FAIL=$((GEN_FAIL + 1))
    fi
done

PHASE2_END=$(date +%s)
PHASE2_ELAPSED=$(( PHASE2_END - PHASE2_START ))

echo ""
echo "══════════════════════════════════════════════════"
echo " BATCH COMPLETE"
echo " Phase 1 (Offline):  OK=${OFFLINE_OK} FAIL=${OFFLINE_FAIL} Time=${PHASE1_ELAPSED}s"
echo " Phase 2 (Generate): OK=${GEN_OK} FAIL=${GEN_FAIL} Time=${PHASE2_ELAPSED}s"
echo " Total: $(( PHASE1_ELAPSED + PHASE2_ELAPSED ))s"
echo " Log:   ${LOG_FILE}"
echo "══════════════════════════════════════════════════"
