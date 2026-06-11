#!/bin/bash
# V19 生产环境启动脚本
# 日期: 2026-04-13
# 版本: V19 (模板库 + V15 审计器)

echo "=========================================="
echo "V19 Production Startup Script"
echo "=========================================="
echo ""

# 检查当前目录
if [ ! -f "run_v17_production.py" ]; then
    echo "[ERROR] run_v17_production.py not found"
    echo "Please run this script from: ~/ADVTEST/DATA_new/code/official_pipeline"
    exit 1
fi

# 检查必要文件
echo "[Check] Verifying required files..."
required_files=(
    "run_method_a.py"
    "semantic_auditor_v15.py"
    "gap_pipeline/template_library.py"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  [OK] $file"
    else
        echo "  [ERROR] $file missing"
        exit 1
    fi
done

echo ""
echo "[Check] All required files present"
echo ""

# 设置环境变量
echo "=========================================="
echo "Setting Environment Variables"
echo "=========================================="

# V19 核心配置
export VQA_USE_V15_AUDITOR=true
export VQA_QUESTION_MODE=template
export VQA_MIN_REAL_MS=0

# Context Cypher 配置
export VQA_CONTEXT_CYPHER_MODE=batch_llm
export VQA_CTX_BATCH_STRATEGY=hybrid
export VQA_CTX_HINT_MAX_TOKENS=1280
export VQA_CTX_BATCH_CHUNK_SIZE=8
export VQA_CTX_BATCH_N_WORKERS=4

# Excel 批量写入
export VQA_EXCEL_BATCH_WRITE=true

# 问题生成配置
export VQA_Q_LLM_CHUNK_SIZE=32

# LLM 超时配置
export VQA_LLM_TIMEOUT_READ=240

echo "  VQA_USE_V15_AUDITOR=$VQA_USE_V15_AUDITOR"
echo "  VQA_QUESTION_MODE=$VQA_QUESTION_MODE"
echo "  VQA_MIN_REAL_MS=$VQA_MIN_REAL_MS"
echo "  VQA_CONTEXT_CYPHER_MODE=$VQA_CONTEXT_CYPHER_MODE"
echo "  VQA_EXCEL_BATCH_WRITE=$VQA_EXCEL_BATCH_WRITE"
echo ""

# 检测服务器编号
if [ -z "$ADVTEST_FRAME_PLAN_JSON" ]; then
    echo "[ERROR] ADVTEST_FRAME_PLAN_JSON not set"
    echo "Please set it to one of:"
    echo "  export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server1.json"
    echo "  export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server2.json"
    echo "  export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server3.json"
    exit 1
fi

# 从路径中提取服务器编号
if [[ "$ADVTEST_FRAME_PLAN_JSON" == *"server1"* ]]; then
    SERVER_NUM=1
elif [[ "$ADVTEST_FRAME_PLAN_JSON" == *"server2"* ]]; then
    SERVER_NUM=2
elif [[ "$ADVTEST_FRAME_PLAN_JSON" == *"server3"* ]]; then
    SERVER_NUM=3
else
    echo "[ERROR] Cannot determine server number from ADVTEST_FRAME_PLAN_JSON"
    exit 1
fi

LOG_FILE=~/ADVTEST/DATA_new/v19_server${SERVER_NUM}.log
PID_FILE=~/ADVTEST/DATA_new/v19_server${SERVER_NUM}.pid

echo "=========================================="
echo "Server Configuration"
echo "=========================================="
echo "  Server: $SERVER_NUM"
echo "  Plan: $ADVTEST_FRAME_PLAN_JSON"
echo "  Log: $LOG_FILE"
echo "  PID: $PID_FILE"
echo ""

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "[WARN] V19 already running (PID: $OLD_PID)"
        echo "Do you want to stop it and restart? (y/n)"
        read -r response
        if [ "$response" = "y" ]; then
            echo "Stopping old process..."
            kill "$OLD_PID"
            sleep 2
        else
            echo "Aborted"
            exit 0
        fi
    fi
fi

# 启动
echo "=========================================="
echo "Starting V19 Production"
echo "=========================================="
echo ""
echo "Command: nohup python -u run_v17_production.py > $LOG_FILE 2>&1 &"
echo ""
echo "Starting in 3 seconds..."
sleep 1
echo "2..."
sleep 1
echo "1..."
sleep 1

nohup python -u run_v17_production.py > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

echo ""
echo "=========================================="
echo "V19 Started Successfully"
echo "=========================================="
echo "  PID: $NEW_PID"
echo "  Log: $LOG_FILE"
echo ""
echo "Monitor progress:"
echo "  tail -f $LOG_FILE"
echo ""
echo "Check status:"
echo "  ps -p $NEW_PID"
echo ""
echo "Stop:"
echo "  kill $NEW_PID"
echo ""
echo "Verify V19 features:"
echo "  grep 'Using V15 auditor' $LOG_FILE"
echo "  grep 'Question Build.*mode=template' $LOG_FILE"
echo "  grep 'Baseline L2' $LOG_FILE"
echo ""
echo "=========================================="
