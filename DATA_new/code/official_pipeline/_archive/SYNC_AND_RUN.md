# V18 批量运行完整指南

## 1. 同步文件到服务器

```bash
# 在本地 PowerShell 执行
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\analyze_and_create_plans.py yunyang@server:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\monitor_progress.py yunyang@server:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_method_a.py yunyang@server:~/ADVTEST/DATA_new/code/official_pipeline/
```

## 2. 生成帧计划（服务器上执行）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
python analyze_and_create_plans.py
```

这会生成两个计划文件：
- `~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_small.json` - 小节点帧（<15节点）
- `~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_12h.json` - 12小时混合计划（200小+50中）

## 3. 启动批量运行

### 方案A：使用12小时混合计划（推荐）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 设置环境变量指向12小时计划
export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_12h.json

# 启动批量运行（后台运行，输出到日志）
nohup python -u run_v17_production.py > ~/ADVTEST/DATA_new/v18_12h_run.log 2>&1 &

# 记录进程ID
echo $! > ~/ADVTEST/DATA_new/v18_run.pid
```

### 方案B：使用小节点计划（更保守）

```bash
export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_small.json
nohup python -u run_v17_production.py > ~/ADVTEST/DATA_new/v18_small_run.log 2>&1 &
echo $! > ~/ADVTEST/DATA_new/v18_run.pid
```

## 4. 实时监控进度

在另一个终端窗口：

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
python monitor_progress.py
```

监控窗口会显示：
- 已完成帧数
- 当前处理的帧（scene-X/fY）
- 当前轮次和已生成问题数
- L0/L1/L2A/L2B 覆盖率进度条
- 平均每题耗时
- 预计剩余时间

按 `Ctrl+C` 退出监控（不影响后台任务）

## 5. 检查运行状态

```bash
# 查看进程是否在运行
ps -p $(cat ~/ADVTEST/DATA_new/v18_run.pid)

# 实时查看日志尾部
tail -f ~/ADVTEST/DATA_new/v18_12h_run.log

# 查看最近的错误
grep -i error ~/ADVTEST/DATA_new/v18_12h_run.log | tail -20
```

## 6. 停止运行（如需要）

```bash
# 优雅停止
kill $(cat ~/ADVTEST/DATA_new/v18_run.pid)

# 强制停止（如果优雅停止无效）
kill -9 $(cat ~/ADVTEST/DATA_new/v18_run.pid)
```

## 7. 查看结果

运行完成后，结果保存在：
```
~/ADVTEST/DATA_new/code/official_pipeline/output/coverage_analysis/nuscenes_qa_coverage_v18.xlsx
```

## 关键配置说明

### V18 改进点

1. **Gap 优先级修复**：优先覆盖 L0/L1，避免重复覆盖相同 L2 路径
   - Stage 1 (L0<100% 或 L1<80%)：L0权重=100, L1权重=50
   - Stage 2 (L1<100%)：L0权重=50, L1权重=20
   - Stage 3 (L1=100%)：L0权重=10, L1权重=5

2. **批量大小优化**：
   - `VQA_Q_LLM_CHUNK_SIZE=47` - 外层分块大小
   - `VQA_Q_MAX_SAFE_BATCH_SIZE=47` - 内层安全批量大小
   - 94题 → 2批 → 约50-70秒

3. **帧选择策略**：
   - 小节点帧（<15节点）：L2数量在几百到几千，可快速完成
   - 中节点帧（15-20节点）：L2数量在几千到几万，适度耗时
   - 避免大节点帧（>30节点）：L2数量十万级，单帧需数小时

## 预期性能

- **平均每题耗时**：0.6-0.8秒（包括LLM生成+Neo4j验证+Excel写入）
- **小节点帧**：每帧约10-30轮，生成600-1800题，耗时10-30分钟
- **中节点帧**：每帧约30-80轮，生成1800-4800题，耗时30-90分钟
- **12小时计划**：200小帧+50中帧，预计生成30-50万题

## 故障排查

### 问题1：LLM 批量超时
```bash
# 检查日志中是否有 "Request timed out"
grep "timed out" ~/ADVTEST/DATA_new/v18_12h_run.log

# 如果频繁超时，降低批量大小
export VQA_Q_LLM_CHUNK_SIZE=32
export VQA_Q_MAX_SAFE_BATCH_SIZE=32
```

### 问题2：Neo4j 连接失败
```bash
# 检查 Neo4j 是否运行
systemctl status neo4j

# 重启 Neo4j
sudo systemctl restart neo4j
```

### 问题3：内存不足
```bash
# 监控内存使用
watch -n 5 free -h

# 如果内存紧张，减少并发数
export VQA_CTX_BATCH_N_WORKERS=2
```

### 问题4：磁盘空间不足
```bash
# 检查磁盘空间
df -h ~/ADVTEST

# 清理旧日志
rm ~/ADVTEST/DATA_new/*.log.old
```

## 完成后验证

```bash
# 统计生成的问题总数
python -c "
import openpyxl
wb = openpyxl.load_workbook('output/coverage_analysis/nuscenes_qa_coverage_v18.xlsx')
ws = wb.active
print(f'总问题数: {ws.max_row - 1}')
"

# 检查覆盖率
grep "Final Coverage" ~/ADVTEST/DATA_new/v18_12h_run.log | tail -1
```
