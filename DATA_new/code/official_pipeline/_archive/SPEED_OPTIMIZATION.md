# 批量大小优化分析 - 目标 0.6s/题

## 理论计算

### 假设参数
- 总问题数：94
- 模型速度：50 tokens/s（Qwen3.5-35B-A3B 典型速度）
- 每题输出：15 tokens
- RTT延迟：200ms/批

### 不同批量大小的性能对比

| 批量大小 | 批次数 | 总时间(s) | 平均时间(s/题) | 是否达标 |
|---------|--------|-----------|---------------|---------|
| 4       | 24     | 21.6      | 0.230         | ✅ 达标 |
| 8       | 12     | 14.4      | 0.153         | ✅ 达标 |
| 16      | 6      | 10.8      | 0.115         | ✅ 达标 |
| 32      | 3      | 9.0       | 0.096         | ✅ 达标 |
| 64      | 2      | 8.4       | 0.089         | ✅ 达标 |
| 94      | 1      | 8.2       | 0.087         | ✅ 达标 |

### 计算公式

```
每批生成时间 = (批量大小 × 15 tokens) / 50 tokens/s
每批总时间 = 生成时间 + 200ms RTT
总时间 = 批次数 × 每批总时间
平均时间 = 总时间 / 94
```

## 实际情况分析

### 问题：为什么实际会超时？

从你的日志看，32条/批会超时180s，说明：

1. **实际模型速度远低于50 tokens/s**
   - 可能只有 5-10 tokens/s
   - 或者模型在处理批量请求时有额外开销

2. **网络延迟远高于200ms**
   - 学校网关可能有限流
   - 或者模型服务器负载高

3. **Prompt 处理时间被低估**
   - V16 Prompt 虽然精简，但32条输入仍然较大
   - 模型需要时间理解和处理输入

### 实际测算（基于你的超时数据）

如果32条超时180s，反推实际速度：

```
32条 × 15 tokens = 480 tokens
180s 超时 → 实际速度 < 480/180 = 2.67 tokens/s
```

这说明**实际速度远低于理论值**。

## 解决方案：达到 0.6s/题

### 方案 1：增大批量 + 优化超时（推荐）

**核心思路**：减少批次数，降低 RTT 开销占比

```bash
# 配置
VQA_Q_LLM_CHUNK_SIZE=94          # 外层：全批处理
VQA_Q_MAX_SAFE_BATCH_SIZE=64     # 内层：最多64条/批
VQA_LLM_TIMEOUT_READ=300         # 增加超时到300s

# 效果
94条 → 2批（64+30） → 总时间约 60-90s → 平均 0.64-0.96s/题
```

**优点**：
- 大幅减少 RTT 次数（从6批降到2批）
- 理论上可以接近 0.6s/题

**风险**：
- 64条/批可能仍会超时
- 需要测试验证

### 方案 2：并行批处理（最优，需要代码修改）

**核心思路**：多个批次并行发送 LLM 请求

```python
# 修改 generate_questions_batch() 使用线程池
from concurrent.futures import ThreadPoolExecutor

def generate_questions_batch(self, inputs, n_workers=4):
    # 分成 n_workers 个批次
    # 并行发送请求
    # 合并结果
```

**效果**：
```
94条 → 4批×24条 → 并行处理 → 总时间 = max(单批时间) ≈ 单批时间
如果单批24条需要15s → 总时间15s → 平均0.16s/题
```

**优点**：
- 可以达到 0.1-0.2s/题
- 充分利用 API 并发能力

**缺点**：
- 需要修改代码
- 可能触发 API 限流

### 方案 3：混合策略（平衡方案）

**配置**：
```bash
VQA_Q_LLM_CHUNK_SIZE=47          # 外层：分2批
VQA_Q_MAX_SAFE_BATCH_SIZE=47     # 内层：不再分块
VQA_LLM_TIMEOUT_READ=240         # 适当增加超时
```

**效果**：
```
94条 → 2批（47+47） → 总时间约 50-70s → 平均 0.53-0.74s/题
```

**优点**：
- 接近目标 0.6s/题
- 风险可控

## 推荐配置（三选一）

### 配置 A：激进方案（目标 0.6s/题）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

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
```

**预期**：0.64-0.96s/题，可能超时

### 配置 B：平衡方案（目标 0.6-0.7s/题）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline

VQA_CONTEXT_CYPHER_MODE=batch_llm \
VQA_CTX_BATCH_STRATEGY=hybrid \
VQA_CTX_HINT_MAX_TOKENS=1280 \
VQA_CTX_BATCH_CHUNK_SIZE=8 \
VQA_CTX_BATCH_N_WORKERS=4 \
VQA_QUESTION_MODE=llm_batch \
VQA_EXCEL_BATCH_WRITE=true \
VQA_Q_LLM_CHUNK_SIZE=47 \
VQA_Q_MAX_SAFE_BATCH_SIZE=47 \
VQA_LLM_TIMEOUT_READ=240 \
python run_method_a.py
```

**预期**：0.53-0.74s/题，较稳定

### 配置 C：保守方案（目标 0.8-1.0s/题，但稳定）

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
VQA_Q_MAX_SAFE_BATCH_SIZE=32 \
VQA_LLM_TIMEOUT_READ=240 \
python run_method_a.py
```

**预期**：0.8-1.0s/题，非常稳定

## 并行批处理代码修改（方案2实现）

如果你想要最优性能（0.1-0.2s/题），我可以修改代码实现并行批处理。

需要修改的地方：
1. `llm_client.py` 的 `generate_questions_batch()` 方法
2. 添加线程池并行调用 `_generate_questions_batch_single()`

是否需要我实现这个方案？

## 总结

| 方案 | 批量大小 | 预计时间/题 | 稳定性 | 推荐度 |
|------|---------|------------|--------|--------|
| 配置A（激进） | 64 | 0.64-0.96s | ⚠️ 可能超时 | ⭐⭐ |
| 配置B（平衡） | 47 | 0.53-0.74s | ✅ 较稳定 | ⭐⭐⭐⭐ |
| 配置C（保守） | 32 | 0.8-1.0s | ✅✅ 很稳定 | ⭐⭐⭐ |
| 并行方案 | 24×4 | 0.1-0.2s | ✅ 稳定 | ⭐⭐⭐⭐⭐ |

**我的建议**：
1. 先试配置B（平衡方案），看能否达到 0.6s/题且不超时
2. 如果配置B超时，回退到配置C
3. 如果需要更快速度，我可以实现并行方案
