#!/bin/bash
###############################################################################
# Post-Experiment Tasks — 后台一键执行
# 任务1: 全量 L2 覆盖率验证 (6011帧 meta文件)
# 任务2: 清理 _generated.* Legacy冗余文件 (节省存储)
# 任务3: 数据统计报告
#
# 使用: nohup bash /home/yunyang/ADVTEST/DATA_new/scripts/post_experiment_tasks.sh \
#       > /home/yunyang/ADVTEST/DATA_new/outputs/post_experiment.log 2>&1 &
###############################################################################

set -euo pipefail

OUTPUTS_DIR="/mnt/data4/yunyang/ADVTEST_DATA/outputs"
REPORT_DIR="/home/yunyang/ADVTEST/DATA_new/outputs"
REPORT_FILE="${REPORT_DIR}/post_experiment_report.txt"
STATS_CSV="${REPORT_DIR}/all_frames_stats.csv"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Helper: extract value from meta CSV (handles \r from NTFS)
get_meta_val() {
    local file="$1"
    local key="$2"
    grep "^${key}," "$file" 2>/dev/null | cut -d',' -f2 | tr -d '\r\n'
}

echo "============================================================"
echo "  Post-Experiment Tasks Started: ${TIMESTAMP}"
echo "============================================================"
echo ""

###############################################################################
# TASK 1: 全量 L2 覆盖率验证
###############################################################################
echo "================================================================"
echo "  TASK 1/3: 全量 L2 覆盖率验证"
echo "================================================================"

TOTAL=0
PASS=0
FAIL=0
MISSING_META=0
NO_QA_DIR=0
FAIL_LIST=""

for frame_dir in "${OUTPUTS_DIR}"/scene-*; do
    [ -d "$frame_dir" ] || continue
    TOTAL=$((TOTAL + 1))

    frame_name=$(basename "$frame_dir")
    qa_dir="${frame_dir}/generation/qa"
    meta_file="${qa_dir}/${frame_name}_generated_meta.csv"

    if [ ! -d "$qa_dir" ]; then
        NO_QA_DIR=$((NO_QA_DIR + 1))
        FAIL=$((FAIL + 1))
        FAIL_LIST="${FAIL_LIST}${frame_name}: NO_QA_DIR\n"
        continue
    fi

    if [ ! -f "$meta_file" ]; then
        MISSING_META=$((MISSING_META + 1))
        FAIL=$((FAIL + 1))
        FAIL_LIST="${FAIL_LIST}${frame_name}: MISSING_META\n"
        continue
    fi

    total_gaps=$(get_meta_val "$meta_file" "total_l2_gaps")
    final_cov=$(get_meta_val "$meta_file" "final_coverage_l2")

    if [ -z "$total_gaps" ] || [ -z "$final_cov" ]; then
        FAIL=$((FAIL + 1))
        FAIL_LIST="${FAIL_LIST}${frame_name}: INVALID_META (gaps=${total_gaps:-null} cov=${final_cov:-null})\n"
        continue
    fi

    if [ "$total_gaps" = "$final_cov" ] && [ "$total_gaps" -gt 0 ]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        rate=$(echo "scale=4; $final_cov / $total_gaps" | bc 2>/dev/null || echo "N/A")
        FAIL_LIST="${FAIL_LIST}${frame_name}: L2=${final_cov}/${total_gaps} (${rate})\n"
    fi

    if [ $((TOTAL % 500)) -eq 0 ]; then
        echo "  [Task1] Progress: ${TOTAL} frames checked, PASS=${PASS} FAIL=${FAIL}"
    fi
done

echo ""
echo "──────────────────────────────────────────"
echo "  TASK 1 RESULT: L2 覆盖率验证"
echo "──────────────────────────────────────────"
echo "  Total frames:   ${TOTAL}"
echo "  PASS (100%):    ${PASS}"
echo "  FAIL:           ${FAIL}"
echo "    - NO_QA_DIR:    ${NO_QA_DIR}"
echo "    - MISSING_META: ${MISSING_META}"
if [ "$FAIL" -gt 0 ]; then
    echo "  Failed frames:"
    echo -e "$FAIL_LIST" | head -50
fi
echo "─���────────────────────────────────────────"
echo ""

###############################################################################
# TASK 2: 清理 _generated.* Legacy冗余文件
# _generated.jsonl 与 _all.jsonl 完全相同 (md5 verified)
# _generated.csv 比 _all.csv 多了 delta/cum 列但数据等价
# 保留: _all.*, _round1.*, _round2.*, _generated_meta.csv
# 删除: _generated.csv, _generated.jsonl
###############################################################################
echo "================================================================"
echo "  TASK 2/3: 清理 Legacy 冗余文件"
echo "================================================================"

DEL_COUNT=0
DEL_SIZE_BYTES=0

echo "  Phase 2a: 统计冗余文件..."
for frame_dir in "${OUTPUTS_DIR}"/scene-*; do
    [ -d "$frame_dir" ] || continue
    frame_name=$(basename "$frame_dir")
    qa_dir="${frame_dir}/generation/qa"
    [ -d "$qa_dir" ] || continue

    for suffix in "_generated.csv" "_generated.jsonl"; do
        f="${qa_dir}/${frame_name}${suffix}"
        if [ -f "$f" ]; then
            fsize=$(stat -c %s "$f" 2>/dev/null || echo 0)
            DEL_SIZE_BYTES=$((DEL_SIZE_BYTES + fsize))
            DEL_COUNT=$((DEL_COUNT + 1))
        fi
    done
done

DEL_SIZE_GB=$(echo "scale=1; $DEL_SIZE_BYTES / 1024 / 1024 / 1024" | bc 2>/dev/null || echo "N/A")
echo "  Files to delete: ${DEL_COUNT}"
echo "  Space to free:   ~${DEL_SIZE_GB} GB"
echo ""

echo "  Phase 2b: 验证 JSONL 等价性 (抽样50帧) ..."
VERIFIED=0
VERIFY_FAIL=0
SAMPLE_COUNT=0
for frame_dir in "${OUTPUTS_DIR}"/scene-*; do
    [ -d "$frame_dir" ] || continue
    [ $SAMPLE_COUNT -ge 50 ] && break

    frame_name=$(basename "$frame_dir")
    qa_dir="${frame_dir}/generation/qa"
    gen_jsonl="${qa_dir}/${frame_name}_generated.jsonl"
    all_jsonl="${qa_dir}/${frame_name}_all.jsonl"

    if [ -f "$gen_jsonl" ] && [ -f "$all_jsonl" ]; then
        md5_gen=$(md5sum "$gen_jsonl" | awk '{print $1}')
        md5_all=$(md5sum "$all_jsonl" | awk '{print $1}')
        if [ "$md5_gen" = "$md5_all" ]; then
            VERIFIED=$((VERIFIED + 1))
        else
            VERIFY_FAIL=$((VERIFY_FAIL + 1))
            echo "    MISMATCH: ${frame_name}"
        fi
        SAMPLE_COUNT=$((SAMPLE_COUNT + 1))
    fi
done

echo "  JSONL verify: ${VERIFIED}/${SAMPLE_COUNT} identical, ${VERIFY_FAIL} mismatches"

DELETED=0
if [ "$VERIFY_FAIL" -gt 0 ]; then
    echo "  ⚠️  有不一致, 跳过删除!"
else
    echo ""
    echo "  Phase 2c: 执行删除..."
    for frame_dir in "${OUTPUTS_DIR}"/scene-*; do
        [ -d "$frame_dir" ] || continue
        frame_name=$(basename "$frame_dir")
        qa_dir="${frame_dir}/generation/qa"
        [ -d "$qa_dir" ] || continue

        for suffix in "_generated.csv" "_generated.jsonl"; do
            f="${qa_dir}/${frame_name}${suffix}"
            if [ -f "$f" ]; then
                rm -f "$f"
                DELETED=$((DELETED + 1))
            fi
        done

        if [ $((DELETED % 1000)) -eq 0 ] && [ $DELETED -gt 0 ]; then
            echo "    [Task2] Deleted ${DELETED} files..."
        fi
    done
    echo ""
    echo "  ✅ Deleted ${DELETED} files, freed ~${DEL_SIZE_GB} GB"
fi
echo "──────────────────────────────────────────"
echo ""

###############################################################################
# TASK 3: 数据统计报告
###############################################################################
echo "================================================================"
echo "  TASK 3/3: 数据统计报告"
echo "================================================================"

TOTAL_QA=0
TOTAL_GAPS=0

# 写入 per-frame CSV
echo "scene_frame,filtered_nodes,total_l2_gaps,generated_questions,final_coverage_l2" > "$STATS_CSV"

for frame_dir in "${OUTPUTS_DIR}"/scene-*; do
    [ -d "$frame_dir" ] || continue
    frame_name=$(basename "$frame_dir")
    meta="${frame_dir}/generation/qa/${frame_name}_generated_meta.csv"
    [ -f "$meta" ] || continue

    nodes=$(get_meta_val "$meta" "filtered_nodes")
    gaps=$(get_meta_val "$meta" "total_l2_gaps")
    gen_q=$(get_meta_val "$meta" "generated_questions")
    cov=$(get_meta_val "$meta" "final_coverage_l2")

    TOTAL_QA=$((TOTAL_QA + ${gen_q:-0}))
    TOTAL_GAPS=$((TOTAL_GAPS + ${gaps:-0}))

    echo "${frame_name},${nodes:-?},${gaps:-?},${gen_q:-?},${cov:-?}" >> "$STATS_CSV"
done

# Write summary report
{
echo "============================================================"
echo "  ADVTEST VQA Pipeline — 实验完成报告"
echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""
echo "## 1. 全局状态"
echo "  Total frames:         ${TOTAL}"
echo "  L2 100% PASS:         ${PASS}"
echo "  L2 FAIL:              ${FAIL}"
echo "  Total L2 gaps:        ${TOTAL_GAPS}"
echo "  Total QA generated:   ${TOTAL_QA}"
echo ""
echo "## 2. 清理结果"
echo "  Deleted legacy files: ${DELETED}"
echo "  Space freed:          ~${DEL_SIZE_GB} GB"
echo ""
echo "## 3. 磁盘使用"
df -h /home/yunyang /mnt/data4 2>/dev/null | sed 's/^/  /'
echo ""
echo "  Outputs directory:"
du -sh "${OUTPUTS_DIR}" 2>/dev/null | sed 's/^/  /'
echo ""
echo "## 4. Per-frame stats"
echo "  CSV: ${STATS_CSV}"
echo "  (${TOTAL} rows)"
} > "$REPORT_FILE"

echo "  ✅ Report:     ${REPORT_FILE}"
echo "  ✅ Stats CSV:  ${STATS_CSV}"
echo ""
echo "──────────────────────────────────────────"
echo "  TASK 3 SUMMARY"
echo "──────────────────────────────────────────"
echo "  Total frames:       ${TOTAL}"
echo "  L2 PASS:            ${PASS} / ${TOTAL}"
echo "  Total L2 gaps:      ${TOTAL_GAPS}"
echo "  Total QA generated: ${TOTAL_QA}"
echo "──────────────────────────────────────────"
echo ""

ENDTIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "============================================================"
echo "  All Tasks Complete: ${ENDTIME}"
echo "============================================================"
