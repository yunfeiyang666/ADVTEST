#!/bin/bash
# V17 超时修复版本 - 快速启动脚本
# 使用方法：bash run_v17_fixed.sh

cd ~/ADVTEST/DATA_new/code/official_pipeline

echo "=========================================="
echo "  V17 超时修复版 - Method A 执行"
echo "=========================================="
echo ""
echo "配置："
echo "  - 批量模式：llm_batch"
echo "  - 外层分块：32条/批"
echo "  - 内层安全分块：16条/批（V17新增）"
echo "  - 超时时间：180秒"
echo ""
echo "预计效果："
echo "  - 94条问题 → 6批 × 16条"
echo "  - 不会出现超时错误"
echo ""
echo "开始执行..."
echo ""

VQA_CONTEXT_CYPHER_MODE=batch_llm \
VQA_CTX_BATCH_STRATEGY=hybrid \
VQA_CTX_HINT_MAX_TOKENS=1280 \
VQA_CTX_BATCH_CHUNK_SIZE=8 \
VQA_CTX_BATCH_N_WORKERS=4 \
VQA_QUESTION_MODE=llm_batch \
VQA_EXCEL_BATCH_WRITE=true \
VQA_Q_LLM_CHUNK_SIZE=32 \
VQA_Q_MAX_SAFE_BATCH_SIZE=16 \
VQA_LLM_TIMEOUT_READ=180 \
python run_method_a.py

echo ""
echo "=========================================="
echo "  执行完成"
echo "=========================================="
