#!/bin/bash
# 激进方案 - 目标 0.6s/题（可能超时，需测试）
# 使用方法：bash run_v17_aggressive.sh

cd ~/ADVTEST/DATA_new/code/official_pipeline

echo "=========================================="
echo "  V17 激进方案 - 目标 0.6s/题"
echo "=========================================="
echo ""
echo "配置："
echo "  - 批量模式：llm_batch"
echo "  - 外层分块：94条/批（全批）"
echo "  - 内层安全分块：64条/批"
echo "  - 超时时间：300秒"
echo ""
echo "预计效果："
echo "  - 94条问题 → 2批（64+30）"
echo "  - 总时间约 60-90秒"
echo "  - 平均 0.64-0.96s/题"
echo ""
echo "⚠️  警告：此配置可能超时，建议先测试"
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
VQA_Q_LLM_CHUNK_SIZE=94 \
VQA_Q_MAX_SAFE_BATCH_SIZE=64 \
VQA_LLM_TIMEOUT_READ=300 \
python run_method_a.py

echo ""
echo "=========================================="
echo "  执行完成"
echo "=========================================="
