# 代码精修进度报告

## 已完成：无向边规范化 + 覆盖真实性验证（V7）

### 修改日期
2026-04-23

### 核心修改内容

#### 1. 无向边规范化（coverage_tracker.py）

**新增规范化函数**：
```python
def _l1_key_normalized(src_id: str, tgt_id: str) -> str:
    """L1 key (normalized): 按字典序排序，实现无向边"""
    if src_id <= tgt_id:
        return f"{src_id}->{tgt_id}"
    else:
        return f"{tgt_id}->{src_id}"

def _l2_key_normalized(n1: str, n2: str, n3: str) -> str:
    """L2 key (normalized): 按首尾节点字典序，实现无向路径"""
    if n1 <= n3:
        return f"{n1}->{n2}->{n3}"
    else:
        return f"{n3}->{n2}->{n1}"
```

**原始方向追踪**：
- 添加 `_L1_original_directions: Dict[str, List[Tuple[str, str]]]`
- 添加 `_L2_original_directions: Dict[str, List[Tuple[str, str, str]]]`
- 在 `init_from_session` 中记录所有原始方向用于审计

**覆盖记录更新**：
- `init_from_session` 使用规范化key存储L1/L2
- `record_from_qa` 使用规范化key记录覆盖

#### 2. 覆盖真实性验证

**新增验证函数**：
```python
def verify_authentic_coverage(
    self,
    session,
    qa: Dict[str, Any],
    cypher_query: str,
    query_results: List[Dict]
) -> Dict[str, Any]:
    """
    验证覆盖的真实性
    
    Returns:
        {
            "is_authentic": bool,
            "structural_match": bool,  # Cypher包含目标节点
            "semantic_match": bool,    # 结果匹配预期路径
            "reason": str
        }
    """
```

**验证逻辑**：
1. 结构匹配：检查Cypher查询是否包含目标节点
2. 语义匹配：检查返回结果是否包含目标路径
3. 只有两者都通过才记录为真实覆盖

**集成方法**：
```python
def record_from_qa_with_verification(
    self,
    session,
    qa: Dict[str, Any],
    cypher_query: str = "",
    query_results: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """带验证的覆盖记录"""
```

#### 3. L2A/L2B统一为L2

**config.py**：
- `L2A_CONTEXT_PROMPT` → `L2_CONTEXT_PROMPT`（统一L2路径）
- `L2B_CONTEXT_PROMPT` → `L2_INTERACTION_CONTEXT_PROMPT`（特殊的ego双臂交互）
- 保留向后兼容别名

**llm_client.py**：
- `generate_l2a_context_cypher` → 调用统一的 `generate_l2_context_cypher`
- `build_l2a_fallback_cypher` → 调用统一的 `build_l2_fallback_cypher`
- `generate_context_cypher_batch` 支持 `topology="L2"`
- 保留向后兼容方法

#### 4. 测试验证

**规范化函数测试**：
```
_l1_key_normalized("car1", "car2") = car1->car2
_l1_key_normalized("car2", "car1") = car1->car2  ✓

_l2_key_normalized("a", "b", "c") = a->b->c
_l2_key_normalized("c", "b", "a") = a->b->c  ✓
```

### 预期效果

1. **L1边总数减半**：`a->b` 和 `b->a` 只存储一个
2. **L2路径总数减半**：`a->b->c` 和 `c->b->a` 只存储一个
3. **覆盖率统计更准确**：不会因方向不同而重复计算
4. **真实性保证**：只记录真实命中的覆盖
5. **审计能力**：保留原始方向信息

### 下一步工作

1. **运行完整流程测试**：
   - 在真实场景图上初始化tracker
   - 验证L1/L2总数是否约减半
   - 验证覆盖率计算准确性

2. **集成到主流程**：
   - 更新 `run_gap_pipeline` 使用 `record_from_qa_with_verification`
   - 添加真实性统计报告

3. **性能测试**：
   - 测量规范化和验证的性能开销
   - 优化如有必要

### 修改文件清单

- ✅ `gap_pipeline/coverage_tracker.py` - 核心修改
- ✅ `gap_pipeline/config.py` - 统一L2定义
- ✅ `gap_pipeline/llm_client.py` - 更新L2引用
- ✅ `gap_pipeline/template_library.py` - 已无L2A/L2B引用

### 向后兼容性

所有修改保持向后兼容：
- 旧代码中的 `L2A`/`L2B` 标识仍被接受
- `record_from_qa` 自动处理 `topology in ("L2", "L2A", "L2B")`
- 提供别名函数支持旧调用方式
