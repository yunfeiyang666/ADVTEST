# 代码精修进度报告 - 2026-04-23 更新

## 已完成工作

### 1. 统一L2定义 + 无向边规范化（V7）

#### 修改日期
2026-04-23

#### 核心修改

##### 1.1 添加规范化函数
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

##### 1.2 添加原始方向追踪
```python
self._L1_original_directions: Dict[str, List[Tuple[str, str]]] = {}
self._L2_original_directions: Dict[str, List[Tuple[str, str, str]]] = {}
```

##### 1.3 修改初始化逻辑
- `init_from_session` 使用规范化key存储L1/L2
- 同时记录原始方向信息用于审计

##### 1.4 修改覆盖记录逻辑
- `record_from_qa` 使用规范化key记录覆盖

### 2. 覆盖真实性增强（V7）

#### 问题分析
发现约束过程中用到的候选对象（siblings、referents）没有被记录为已覆盖。

**示例**：
```
Gap: ego→car1→car2 (car2是truck)
Siblings: car3(car), car4(car), car5(pedestrian)

问题: "What is the truck to the front of car1?"
答案: car2

这个问题的正确性依赖于：
- car3不是truck ← 需要知道car3的类型
- car4不是truck ← 需要知道car4的类型  
- car5不是truck ← 需要知道car5的类型

当前只记录: ego→car1→car2
应该记录: ego→car1→car2, ego→car1→car3, ego→car1→car4, ego→car1→car5
```

#### 解决方案

##### 2.1 新增方法：record_from_qa_with_candidates
```python
def record_from_qa_with_candidates(
    self,
    qa: Dict[str, Any],
    candidates: List[Dict],
    ctx: Optional[Dict] = None,
) -> None:
    """
    记录覆盖，包括约束过程中涉及的候选对象和referents
    
    1. 记录gap本身
    2. 记录所有候选对象（siblings）
    3. 记录referents（二跳邻居）
    """
```

##### 2.2 修改 run_gap_pipeline_v6.py
- `_process_single_cell` 返回 `candidates` 和 `ctx`
- 覆盖记录时调用 `record_from_qa_with_candidates`

### 3. 覆盖真实性验证（已实现但未启用）

#### 3.1 验证函数
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
    
    1. 结构匹配：检查Cypher是否包含目标节点
    2. 语义匹配：检查返回结果是否包含目标路径
    """
```

#### 3.2 带验证的记录函数
```python
def record_from_qa_with_verification(
    self,
    session,
    qa: Dict[str, Any],
    cypher_query: str = "",
    query_results: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    带验证的覆盖记录
    只有真实覆盖才记录
    """
```

## 预期效果

### 1. 无向边规范化
- **L1边总数**：从 ~N 减少到 ~N/2（去除方向冗余）
- **L2路径总数**：从 ~M 减少到 ~M/2（去除方向冗余）
- **覆盖率统计**：更准确（不会因方向不同重复计算）

### 2. 候选对象覆盖
- **覆盖率显著提升**：每个问题实际覆盖的拓扑比之前多得多
- **示例**：一个使用TypeFilter的L2问题将记录：
  - Gap路径: `ego→car1→car2`
  - Sibling路径: `ego→car1→car3`, `ego→car1→car4`, `ego→car1→car5`
  - 级联L1: `car1→car2`, `car1→car3`, `car1→car4`, `car1→car5`
  - 级联L0: `car2`, `car3`, `car4`, `car5`

## 待完成工作

### 1. 更新其他文件中的L2A/L2B引用
- [ ] `template_library.py` - 移除L2A/L2B区分
- [ ] `constraint_methods.py` - 更新L2A/L2B引用
- [ ] 其他197处引用

### 2. 测试验证
- [ ] 单元测试：规范化函数
- [ ] 集成测试：完整流程
- [ ] 验证L1/L2总数约减半
- [ ] 验证覆盖率提升

### 3. 文档更新
- [ ] 更新 REFACTOR_PROGRESS.md
- [ ] 更新 design(1).md（如果需要）

## 关键文件

### 已修改
- `gap_pipeline/coverage_tracker.py` - 核心修改（V7）
- `run_gap_pipeline_v6.py` - 覆盖记录逻辑

### 待修改
- `gap_pipeline/template_library.py`
- `gap_pipeline/constraint_methods.py`
- `gap_pipeline/coverage_persistence.py`

## 下一步

1. 运行测试验证修改效果
2. 更新template_library.py和constraint_methods.py
3. 完整测试并对比修改前后的覆盖率统计
