# 改进的Gap评分策略 - 优先覆盖L0/L1

## 问题诊断

### 当前问题
1. **L2路径被反复覆盖**：86% 的问题都是 L2B，L0/L1 覆盖慢
2. **评分函数过于简单**：只考虑未覆盖的L0节点数量
3. **缺乏层级优先级**：没有区分 L0 > L1 > L2 的重要性

### 当前评分函数（第1416-1421行）
```python
def _gap_score(cell):
    path = cell.get("path_pattern", "")
    ego_p = 0.5 if "ego" in path else 1.0
    nodes = [cell.get("n1_id",""), cell.get("n2_id",""), cell.get("n3_id","")]
    unc = sum(1 for n in nodes if n and tracker._L0.get(n, CoverageRecord()).hit_count == 0)
    return ego_p * (unc + 1)
```

## 改进方案

### 改进的评分函数

```python
def _gap_score(cell):
    """改进的gap评分函数：优先覆盖L0和L1"""
    # 获取当前覆盖率
    stats = tracker.stats()
    l0_rate = stats["L0"]["covered"] / max(1, stats["L0"]["total"])
    l1_rate = stats["L1"]["covered"] / max(1, stats["L1"]["total"])
    
    # 基础分：未覆盖的L0节点
    nodes = [cell.get("n1_id",""), cell.get("n2_id",""), cell.get("n3_id","")]
    unc_l0 = sum(1 for n in nodes if n and tracker._L0.get(n, CoverageRecord()).hit_count == 0)
    
    # L1边覆盖情况
    unc_l1 = 0
    if cell.get("n1_id") and cell.get("n2_id"):
        edge_key = f"{cell['n1_id']}→{cell['n2_id']}"
        if tracker._L1.get(edge_key, CoverageRecord()).hit_count == 0:
            unc_l1 += 1
    if cell.get("n2_id") and cell.get("n3_id"):
        edge_key = f"{cell['n2_id']}→{cell['n3_id']}"
        if tracker._L1.get(edge_key, CoverageRecord()).hit_count == 0:
            unc_l1 += 1
    
    # ego惩罚
    path = cell.get("path_pattern", "")
    ego_penalty = 0.5 if "ego" in path else 1.0
    
    # 阶段权重
    if l0_rate < 1.0 or l1_rate < 0.8:
        # 阶段1：快速覆盖L0/L1
        score = 100 * unc_l0 + 50 * unc_l1 + 1
    elif l1_rate < 1.0:
        # 阶段2：平衡覆盖
        score = 50 * unc_l0 + 20 * unc_l1 + 1
    else:
        # 阶段3：L2收尾
        score = 10 * unc_l0 + 5 * unc_l1 + 1
    
    return ego_penalty * score
```

## 预期效果

**当前**：77轮，L2B占86%
**改进后**：预计40-50轮，L0/L1快速覆盖

---

**创建时间**：2026-04-12
