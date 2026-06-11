# 三服务器部署完整指令

## 1. 同步所有文件到三台服务器

```bash
# 在本地 PowerShell 执行（替换 server1/server2/server3 为实际服务器地址）

# 同步到 Server 1
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_v17_production.py yunyang@server1:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_method_a.py yunyang@server1:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\monitor_progress_server1.py yunyang@server1:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\deploy\nuscenesqa_val_plan_server1.json yunyang@server1:~/ADVTEST/DATA_new/code/deploy/

# 同步到 Server 2
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_v17_production.py yunyang@server2:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_method_a.py yunyang@server2:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\monitor_progress_server2.py yunyang@server2:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\deploy\nuscenesqa_val_plan_server2.json yunyang@server2:~/ADVTEST/DATA_new/code/deploy/

# 同步到 Server 3
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_v17_production.py yunyang@server3:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\run_method_a.py yunyang@server3:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\official_pipeline\monitor_progress_server3.py yunyang@server3:~/ADVTEST/DATA_new/code/official_pipeline/
scp E:\Project\ADVTEST\DATA_new\code\deploy\nuscenesqa_val_plan_server3.json yunyang@server3:~/ADVTEST/DATA_new/code/deploy/
```

## 2. Server 1 启动（小节点，1275帧）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server1.json
nohup python -u run_v17_production.py > ~/ADVTEST/DATA_new/v18_server1.log 2>&1 &
echo $! > ~/ADVTEST/DATA_new/v18_server1.pid

# 启动监控
python monitor_progress_server1.py
```

## 3. Server 2 启动（中节点，1182帧）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server2.json
nohup python -u run_v17_production.py > ~/ADVTEST/DATA_new/v18_server2.log 2>&1 &
echo $! > ~/ADVTEST/DATA_new/v18_server2.pid

# 启动监控
python monitor_progress_server2.py
```

## 4. Server 3 启动（大节点，600帧）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
export ADVTEST_FRAME_PLAN_JSON=~/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_server3.json
nohup python -u run_v17_production.py > ~/ADVTEST/DATA_new/v18_server3.log 2>&1 &
echo $! > ~/ADVTEST/DATA_new/v18_server3.pid

# 启动监控
python monitor_progress_server3.py
```

## 5. 使用 tmux 同时查看监控和日志

```bash
tmux
# 上下分屏：Ctrl+b 然后按 "
# 上半部分：python monitor_progress_server1.py
# 下半部分：tail -f ~/ADVTEST/DATA_new/v18_server1.log
```

## 6. 任务分配总结

| 服务器 | 节点范围 | 帧数 | 预计时间 |
|--------|----------|------|----------|
| Server 1 | 0-15节点 | 1275 | 233小时 |
| Server 2 | 15-25节点 | 1182 | 225小时 |
| Server 3 | 25-40节点 | 600 | 249小时 |

总计：3057帧，预计707小时（约29天）
