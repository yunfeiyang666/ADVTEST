# 速度优化方案总结 - 目标 0.6s/题

## 📊 可用方案对比

| 方案 | 脚本名 | 批量大小 | 批次数 | 预计时间/题 | 稳定性 | 推荐度 |
|------|--------|---------|--------|------------|--------|--------|
| **平衡方案** | `run_v17_balanced.sh` | 47 | 2批 | 0.53-0.74s | ✅✅ 推荐 | ⭐⭐⭐⭐⭐ |
| **激进方案** | `run_v17_aggressive.sh` | 64 | 2批 | 0.64-0.96s | ⚠️ 可能超时 | ⭐⭐⭐ |
| **默认方案** | `run_v17_fixed.sh` | 16 | 6批 | 1.0-1.2s | ✅✅✅ 很稳定 | ⭐⭐⭐⭐ |
| **保守方案** | `run_v17_conservative.sh` | 8 | 12批 | 1.5-2.0s | ✅✅✅ 极稳定 | ⭐⭐⭐ |

## 🎯 推荐使用顺序

### 第一选择：平衡方案（最推荐）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
chmod +x run_v17_balanced.sh
bash run_v17_balanced.sh
```

**特点**：
- ✅ 最接近 0.6s/题 目标
- ✅ 稳定性较好
- ✅ 2批处理，RTT开销小
- ⚠️ 如果超时，降级到默认方案

### 第二选择：激进方案（追求极限速度）

```bash
cd ~/ADVTEST/DATA_new/code/official_pipeline
chmod +x run_v17_aggressive.sh
bash run_v17_aggressive.sh
```

**特点**：
- ✅ 理论上可达 0.6s/题
- ⚠️ 64条/批可能超时
- ⚠️ 需要测试验证
- 💡 如果成功，这是最快方案

## 📝 详细配置说明

### 平衡方案配置

```bash
VQA_Q_LLM_CHUNK_SIZE=47          # 外层：分2批
VQA_Q_MAX_SAFE_BATCH_SIZE=47     # 内层：不再分块
VQA_LLM_TIMEOUT_READ=240         # 超时240秒
```

**工作流程**：
```
94条问题 → 外层分2批(47+47) → 内层不分块 → 实际2次请求 → 50-70秒 → 0.53-0.74s/题
```

### 激进方案配置

```bash
VQA_Q_LLM_CHUNK_SIZE=94          # 外层：全批
VQA_Q_MAX_SAFE_BATCH_SIZE=64     # 内层：最多64条
VQA_LLM_TIMEOUT_READ=300         # 超时300秒
```

**工作流程**：
```
94条问题 → 外层1批 → 内层分2批(64+30) → 实际2次请求 → 60-90秒 → 0.64-0.96s/题
```

## 🔍 如何验证是否达到目标

### 查看日志中的关键指标

```bash
# 应该看到
[Question Build] mode=llm_batch cells=94 chunks=2 chunk_size=47 elapsed=56000ms

# 计算平均时间
56000ms / 94 / 1000 = 0.596s/题 ✅ 达标
```

### 不应该看到超时错误

```bash
WARNING V16 batch call failed (Request timed out.)
```

## 🛠️ 故障排查

### 如果平衡方案超时 → 降级到默认方案

```bash
bash run_v17_fixed.sh
```

### 如果激进方案超时 → 降级到平衡方案

```bash
bash run_v17_balanced.sh
```

## 📦 文件清单

已创建的所有文件：

```
E:\Project\ADVTEST\DATA_new\code\official_pipeline\
├── gap_pipeline/llm_client.py         ← 已修改（V17二级分块）
├── run_v17_balanced.sh                ← 平衡方案（47条/批）⭐推荐
├── run_v17_aggressive.sh              ← 激进方案（64条/批）
├── run_v17_fixed.sh                   ← 默认方案（16条/批）
├── run_v17_conservative.sh            ← 保守方案（8条/批）
├── V17_SUMMARY.md                     ← V17总结文档
├── RUN_INSTRUCTIONS.md                ← 详细使用说明
└── SPEED_OPTIMIZATION.md              ← 速度优化分析
```

## 🎯 快速决策

```
想要 0.6s/题？
  ↓
先试平衡方案（47条/批）
  ↓
成功？ → ✅ 完成
  ↓
超时？ → 试激进方案（64条/批）
  ↓
成功？ → ✅ 完成
  ↓
超时？ → 用默认方案（16条/批）
```

---

**最后更新**：2026-04-12  
**推荐方案**：平衡方案（`run_v17_balanced.sh`）  
**目标**：0.6s/题  
**预期**：0.53-0.74s/题
