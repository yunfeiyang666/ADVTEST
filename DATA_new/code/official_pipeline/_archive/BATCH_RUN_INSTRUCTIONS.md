# V18 批量生产执行指令

## 第一步：同步文件到服务器

```bash
scp run_method_a.py yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/
scp gap_pipeline/llm_client.py yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/gap_pipeline/
scp run_v18_batch_production.sh yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/
```

## 第二步：在服务器上执行

```bash
ssh yunyang@server
cd ~/ADVTEST/DATA_new/code/official_pipeline
chmod +x run_v18_batch_production.sh
bash run_v18_batch_production.sh
```

## 监控命令

```bash
# 实时查看日志
tail -f ~/ADVTEST/DATA_new/v18_batch_run.log

# 查看进度
grep -E "Round|Gap Stats|Generated" ~/ADVTEST/DATA_new/v18_batch_run.log | tail -50

# 停止运行
kill $(cat ~/ADVTEST/DATA_new/v18_batch_run.pid)
```

## V18 改进

- Gap优先级优化：优先覆盖L0/L1
- V17二级分块：防止LLM超时
- 预期：每帧40-50轮达到100%覆盖

---
2026-04-12
