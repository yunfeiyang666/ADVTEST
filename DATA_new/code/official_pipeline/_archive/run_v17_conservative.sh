#!/bin/bash
# V17 保守配置版本 - 网络不稳定时使用
# 使用方法：bash run_v17_conservative.sh

cd ~/ADVTEST/DATA_new/code/official_pipeline

echo "=========================================="
echo "  V17 保守配置版 - Method A 执行"
echo "=========================================="
echo ""
echo "配置："
echo "  - 批量模式：llm_batch"
echo "  - 外层分块：32条/批"
echo "  - 内层安全分块：8条/批（保守配置）"
echo "  - 超时时间：240秒"
echo ""
echo "预计效果："
echo "  - 94条问题 → 12批 × 8条"
echo "  - 极度稳定，适合网络不稳定环境"
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
VQA_Q_MAX_SAFE_BATCH_SIZE=8 \
VQA_LLM_TIMEOUT_READ=240 \
python run_method_a.py

echo ""
echo "=========================================="
echo "  执行完成"
echo "=========================================="
