#!/bin/bash
# V18 批量生产运行脚本

# 设置环境变量
export ADVTEST_ROOT=/home/yunyang/ADVTEST/DATA_new
export ADVTEST_RAW_SG_DIR=/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/output/coverage_analysis/scene_graphs
unset PYTHONHOME PYTHONPATH NEO4J_URI NUSCENES_DATAROOT VQA_QA_JSON
export PYTHONUNBUFFERED=1

# 进入工作目录
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 激活环境
conda activate advtest

# 启动批量运行
nohup python run_v17_production.py > "$ADVTEST_ROOT/v18_batch_run.log" 2>&1 &

# 记录进程ID
echo $! > "$ADVTEST_ROOT/v18_batch_run.pid"
echo "批量运行已启动，进程ID: $(cat $ADVTEST_ROOT/v18_batch_run.pid)"
echo "日志: $ADVTEST_ROOT/v18_batch_run.log"

# 监控日志
tail -f "$ADVTEST_ROOT/v18_batch_run.log"
