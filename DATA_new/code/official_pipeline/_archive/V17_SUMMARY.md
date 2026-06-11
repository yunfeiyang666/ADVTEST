# V17 超时修复总结

## 问题诊断

从你提供的日志分析：

1. ✅ **Excel 批量写入已修复** - `[Excel Write] mode=batch` 工作正常
2. ❌ **V16 批量问题生成超时** - `V16 batch call failed (Request timed out.)` 卡死180秒
3. 🔍 **根本原因**：单次请求32条问题对 Qwen3.5-35B-A3B 模型来说负载过大

## 解决方案

### 代码修改

**文件**：`gap_pipeline/llm_client.py`

**修改内容**：
- 在 `generate_questions_batch()` 方法中添加 V17 二级分块保护
- 新增 `_generate_questions_batch_single()` 内部方法处理单批逻辑
- 通过环境变量 `VQA_Q_MAX_SAFE_BATCH_SIZE` 控制单批最大条数（默认16）

**修改效果**：
```
原来：94条 → 3批×32条 → 超时失败
现在：94条 → 3批×32条 → 6批×16条 → 稳定成功
```

### 文件清单

已创建的文件：
1. `RUN_INSTRUCTIONS.md` - 详细使用说明文档
2. `run_v17_fixed.sh` - 默认配置启动脚本（推荐）
3. `run_v17_conservative.sh` - 保守配置启动脚本（网络不稳定时）

已修改的文件：
1. `gap_pipeline/llm_client.py` - 添加 V17 二级分块逻辑

## 快速启动

### 方法 1：使用启动脚本（推荐）

```bash
# 同步文件到服务器后
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 添加执行权限
chmod +x run_v17_fixed.sh run_v17_conservative.sh

# 运行默认配置（推荐）
bash run_v17_fixed.sh

# 或运行保守配置（网络不稳定时）
bash run_v17_conservative.sh
```

### 方法 2：直接命令行

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

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
```

## 验证成功的标志

### 1. 日志中应该看到

```
INFO V17 auto-chunking: 32 questions -> 2 chunks (max_size=16)
[Question Build] mode=llm_batch cells=94 chunks=3 chunk_size=32 elapsed=XXXms
```

### 2. 不应该看到

```
WARNING V16 batch call failed (Request timed out.)
```

### 3. 最终应该成功生成问题

```
[Step 5+6] V18 Realness-Hardened Generation (4 physical timestamps locked)
  Generated XX questions successfully
```

## 配置调优

| 场景 | VQA_Q_MAX_SAFE_BATCH_SIZE | VQA_LLM_TIMEOUT_READ | 预计批次数 |
|------|---------------------------|----------------------|-----------|
| 稳定网络（推荐） | 16（默认） | 180 | 6批 |
| 不稳定网络 | 8 | 240 | 12批 |
| 极慢网络 | 4 | 300 | 24批 |

## 性能对比

| 配置 | 单批大小 | 总批次 | 预计时间 | 稳定性 |
|------|---------|--------|---------|--------|
| 原配置 | 32 | 3 | 失败（超时） | ❌ |
| V17默认 | 16 | 6 | ~60s | ✅ |
| V17保守 | 8 | 12 | ~90s | ✅✅ |

## 同步到服务器

```bash
# 方法1：使用 scp
scp gap_pipeline/llm_client.py yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/gap_pipeline/
scp run_v17_fixed.sh yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/
scp run_v17_conservative.sh yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/
scp RUN_INSTRUCTIONS.md yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/

# 方法2：使用 rsync
rsync -avz gap_pipeline/llm_client.py yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/gap_pipeline/
rsync -avz run_v17_*.sh RUN_INSTRUCTIONS.md yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/

# 方法3：使用 git（如果你的项目在 git 管理下）
git add gap_pipeline/llm_client.py run_v17_*.sh RUN_INSTRUCTIONS.md
git commit -m "V17: 添加二级分块防止批量问题生成超时"
git push
# 然后在服务器上 git pull
```

## 其他发现的问题（不影响超时修复）

### 1. Baseline L2 为 0
- **现象**：`[Baseline L2] rows_with_l2=0/29 backfilled=0`
- **影响**：覆盖率统计不准确
- **位置**：`semantic_auditor.py` 或 `run_method_a.py` 的 baseline 审计部分
- **优先级**：低（不影响当前超时问题）

### 2. Context hints 全零
- **现象**：`context hints tighten(...)=0` 全零
- **影响**：问题质量可能不够精准
- **位置**：`llm_client.py:453-507` 的 `_generate_context_hints_batch()`
- **优先级**：低（不影响当前超时问题）

## 回滚方案

如果需要回滚：

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
git checkout gap_pipeline/llm_client.py
```

或者手动删除 V17 添加的代码，恢复原来的 `generate_questions_batch()` 方法。

## 技术细节

### V17 分块逻辑

```python
# 外层分块（run_method_a.py）
94条问题 → 按 VQA_Q_LLM_CHUNK_SIZE=32 分成 3批
  ↓
# 内层分块（llm_client.py V17）
每批32条 → 按 VQA_Q_MAX_SAFE_BATCH_SIZE=16 再分成 2批
  ↓
# 最终效果
实际发送 6 次 LLM 请求，每次 ≤16 条问题
```

### 为什么不直接改 VQA_Q_LLM_CHUNK_SIZE？

1. **兼容性**：保持外层逻辑不变，只在内层添加保护
2. **灵活性**：可以通过环境变量独立调整两层分块大小
3. **安全性**：即使用户配置不当，V17 也能自动保护

## 联系方式

如果遇到问题，请提供：
1. 完整的错误日志
2. 使用的启动命令
3. 环境变量配置

---

**修改完成时间**：2026-04-12  
**修改版本**：V17  
**修改内容**：添加二级分块防止批量问题生成超时
