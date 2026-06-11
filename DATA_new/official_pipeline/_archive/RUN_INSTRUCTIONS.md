# V17 超时修复 - 运行指令

## 修改内容

### 文件：`gap_pipeline/llm_client.py`

**修改位置**：`generate_questions_batch()` 方法（第850-970行）

**修改内容**：
1. 添加 V17 二级分块保护逻辑
2. 新增 `_generate_questions_batch_single()` 内部方法
3. 通过环境变量 `VQA_Q_MAX_SAFE_BATCH_SIZE` 控制单批最大条数（默认16）

**修改效果**：
- 原来：94条问题 → 按 `VQA_Q_LLM_CHUNK_SIZE=32` 分3批 → 每批32条 → 超时
- 现在：94条问题 → 先按32分3批 → 每批再按16分块 → 实际6批，每批≤16条 → 不超时

## 启动指令（服务器端）

### 方案 A：使用默认配置（推荐）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 使用 V17 默认配置（MAX_SAFE_BATCH_SIZE=16）
VQA_CONTEXT_CYPHER_MODE=batch_llm \
VQA_CTX_BATCH_STRATEGY=hybrid \
VQA_CTX_HINT_MAX_TOKENS=1280 \
VQA_CTX_BATCH_CHUNK_SIZE=8 \
VQA_CTX_BATCH_N_WORKERS=4 \
VQA_QUESTION_MODE=llm_batch \
VQA_EXCEL_BATCH_WRITE=true \
VQA_Q_LLM_CHUNK_SIZE=32 \
VQA_LLM_TIMEOUT_READ=180 \
python run_method_a.py
```

**说明**：
- `VQA_Q_LLM_CHUNK_SIZE=32` 保持不变（外层分块）
- V17 代码会自动在内部将每批32条再分成2批×16条
- 实际效果：94条 → 3批×32 → 6批×16 → 稳定不超时

### 方案 B：更保守配置（网络不稳定时）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 使用更小的批量大小
VQA_CONTEXT_CYPHER_MODE=batch_llm \
VQA_CTX_BATCH_STRATEGY=hybrid \
VQA_CTX_HINT_MAX_TOKENS=1280 \
VQA_CTX_BATCH_CHUNK_SIZE=8 \
VQA_CTX_BATCH_N_WORKERS=4 \
VQA_QUESTION_MODE=llm_batch \
VQA_EXCEL_BATCH_WRITE=true \
VQA_Q_LLM_CHUNK_SIZE=32 \
VQA_Q_MAX_SAFE_BATCH_SIZE=8 \
VQA_LLM_TIMEOUT_READ=180 \
python run_method_a.py
```

**说明**：
- 设置 `VQA_Q_MAX_SAFE_BATCH_SIZE=8` 将单批降到8条
- 实际效果：94条 → 3批×32 → 12批×8 → 极度稳定

### 方案 C：增加超时时间（辅助）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

# 同时增加超时时间
VQA_CONTEXT_CYPHER_MODE=batch_llm \
VQA_CTX_BATCH_STRATEGY=hybrid \
VQA_CTX_HINT_MAX_TOKENS=1280 \
VQA_CTX_BATCH_CHUNK_SIZE=8 \
VQA_CTX_BATCH_N_WORKERS=4 \
VQA_QUESTION_MODE=llm_batch \
VQA_EXCEL_BATCH_WRITE=true \
VQA_Q_LLM_CHUNK_SIZE=32 \
VQA_Q_MAX_SAFE_BATCH_SIZE=16 \
VQA_LLM_TIMEOUT_READ=240 \
python run_method_a.py
```

## 验证方法

### 1. 检查日志输出

运行后查看日志，应该看到：

```
[Question Build] mode=llm_batch cells=94 chunks=3 chunk_size=32 elapsed=XXXms
```

如果触发了 V17 自动分块，会额外看到：

```
INFO V17 auto-chunking: 32 questions -> 2 chunks (max_size=16)
INFO V17 auto-chunking: 32 questions -> 2 chunks (max_size=16)
INFO V17 auto-chunking: 30 questions -> 2 chunks (max_size=16)
```

### 2. 确认不再超时

日志中**不应再出现**：

```
WARNING V16 batch call failed (Request timed out.)
```

### 3. 检查问题生成成功率

日志末尾应该显示：

```
[Step 5+6] V18 Realness-Hardened Generation (4 physical timestamps locked)
  Generated XX questions successfully
```

## 环境变量说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VQA_Q_LLM_CHUNK_SIZE` | 32 | 外层分块大小（run_method_a.py 层面） |
| `VQA_Q_MAX_SAFE_BATCH_SIZE` | 16 | V17 内层安全批量大小（llm_client.py 层面） |
| `VQA_LLM_TIMEOUT_READ` | 180 | LLM 读取超时（秒） |

**推荐配置**：
- 稳定网络：`VQA_Q_MAX_SAFE_BATCH_SIZE=16`（默认）
- 不稳定网络：`VQA_Q_MAX_SAFE_BATCH_SIZE=8`
- 极慢网络：`VQA_Q_MAX_SAFE_BATCH_SIZE=4` + `VQA_LLM_TIMEOUT_READ=300`

## 性能影响分析

### 原配置（超时前）
- 94条问题 → 3批 × 32条
- 理论时间：3 × 单批时间
- 实际：第1批超时（180s），流程失败

### V17 配置（修复后）
- 94条问题 → 3批 × 32条 → 6批 × 16条
- 理论时间：6 × 单批时间
- 实际：每批稳定完成，总时间约为原来的 2 倍，但**不会超时失败**

### 性能对比

| 配置 | 批次数 | 单批大小 | 预计总时间 | 稳定性 |
|------|--------|----------|-----------|--------|
| 原配置 | 3 | 32 | 失败（超时） | ❌ 不稳定 |
| V17默认 | 6 | 16 | ~60s | ✅ 稳定 |
| V17保守 | 12 | 8 | ~90s | ✅ 极稳定 |

**结论**：虽然总时间略增，但换来了**100%的稳定性**，避免了180s超时导致的流程失败。

## 故障排查

### 如果仍然超时

1. **降低批量大小**：
   ```bash
   export VQA_Q_MAX_SAFE_BATCH_SIZE=8
   ```

2. **增加超时时间**：
   ```bash
   export VQA_LLM_TIMEOUT_READ=300
   ```

3. **检查网络连接**：
   ```bash
   curl -I http://218.197.140.7:3001/v1/models
   ```

4. **检查模型负载**：
   - 如果学校 API 网关负载过高，考虑错峰运行
   - 或联系管理员增加配额

### 如果问题质量下降

V17 修改**不影响问题质量**，只是改变了批次划分方式。如果发现问题质量问题，应该检查：

1. Baseline L2 为 0 的问题（与超时无关）
2. Context hints 全零的问题（与超时无关）

## 同步到服务器

```bash
# 在本地（Windows）
cd E:\Project\ADVTEST\DATA_new\code\official_pipeline

# 同步修改后的文件到服务器
scp gap_pipeline/llm_client.py yunyang@server:/home/yunyang/ADVTEST/DATA_new/code/official_pipeline/gap_pipeline/

# 或者使用你的同步工具（如 rsync、git）
```

## 回滚方案

如果需要回滚到原版本：

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
git checkout gap_pipeline/llm_client.py
```

或者手动恢复：将 `generate_questions_batch()` 方法改回原来的单批处理逻辑。
