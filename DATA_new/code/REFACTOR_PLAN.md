# Code Refactoring Plan - 基于 design(1).md 的精修计划

## 目标
基于成熟的 `official_pipeline` 代码，参考 `design(1).md` 规范进行精修，解决：
1. L2定义规范性问题
2. 模板系统清晰化
3. 约束机制明确化
4. 唯一性保证加强
5. 覆盖真实统计准确化

## 核心修改点

### 1. L2定义统一 (最高优先级)

**当前状态：**
- `coverage_tracker.py` 区分 L2A (ego→A→B) 和 L2B (A→B→C, A≠ego)
- 使用不同的key格式

**目标状态（design(1).md 第16-17行）：**
- **不再区分 L2A/L2B**
- 统一为 `gap_state['L2']`
- 键为三跳路径 `path_key`：`a->b->c` 字符串格式

**修改文件：**
- `coverage_tracker.py` - 统一L2定义和key格式
- `constraint_methods.py` - 更新所有L2相关逻辑
- `template_library.py` - 移除L2A/L2B区分
- 所有使用 `L2A`/`L2B` 字符串的地方

**修改细节：**
```python
# 旧代码
def _l2a_key(ego: str, a: str, b: str) -> str:
    return f"{ego}|{a}|{b}"

def _l2b_key(n1: str, n2: str, n3: str) -> str:
    return f"{n1}|{n2}|{n3}"

# 新代码
def _l2_key(n1: str, n2: str, n3: str) -> str:
    """统一的L2路径key: a->b->c"""
    return f"{n1}->{n2}->{n3}"
```

### 2. 约束层级明确化

**当前状态：**
- `constraint_methods.py` 有15层约束方法
- 优先级P1-P15

**目标状态（design(1).md 第28-30行）：**
- **共3层约束**：
  1. `direction` (6向，与 RELATES_TO 的 direction 一致)
  2. `distance_range`
  3. `object_type`

**问题：**
- design(1).md 说3层，但现有代码有15层且更完善
- 需要确认：是简化到3层，还是保留15层但明确前3层为核心？

**建议：**
保留15层约束方法（因为更完善），但：
1. 明确标注核心3层
2. 在文档中说明扩展层的作用
3. 可配置是否启用扩展层

### 3. 模板系统规范化

**当前状态：**
- `template_library.py` 有完整的四级结构
- L0/L1/L2 模板分类清晰

**需要精修：**
1. 移除所有 `L2A`/`L2B` 标识，统一为 `L2`
2. 确保 `required_params` 完整且准确
3. 验证每个模板的 `answer_logic` 有对应实现

### 4. 覆盖真实性验证

**当前状态：**
- `coverage_tracker.py` 有 `mark()` 方法记录覆盖
- 但缺少真实性验证逻辑

**目标状态（design(1).md 第9-10行）：**
> 覆盖的底线：追求真实覆盖。在题目/查询**确实关涉**到对应节点、边、或三连边路径时，才计为有效覆盖。

**需要添加：**
1. `verify_authentic_coverage()` 函数
2. 检查查询结果是否真实命中目标路径
3. 区分"结构命中"和"语义命中"

### 5. 唯一性保证机制

**当前状态：**
- 约束链逐层收束候选集
- 最终fallback到计数/存在性

**需要加强：**
1. 在约束前验证gap的唯一性
2. 记录每层约束后的候选数
3. 如果约束后仍不唯一，记录原因

## 修改顺序

### Phase 1: L2定义统一（核心）
1. 修改 `coverage_tracker.py` 的key格式
2. 更新所有引用L2A/L2B的代码
3. 测试覆盖率计算正确性

### Phase 2: 约束层级文档化
1. 在 `constraint_methods.py` 添加核心3层标注
2. 添加配置选项控制约束层数
3. 更新文档说明

### Phase 3: 模板系统清理
1. 统一模板中的L2标识
2. 验证 `required_params` 完整性
3. 检查 `answer_logic` 实现

### Phase 4: 真实性验证
1. 实现 `verify_authentic_coverage()`
2. 集成到覆盖率更新流程
3. 添加真实性统计

### Phase 5: 测试与验证
1. 单元测试每个修改模块
2. 集成测试完整流程
3. 对比修改前后的覆盖率统计

## 风险与注意事项

1. **向后兼容性**：现有的gap JSON文件可能使用旧格式
   - 需要迁移脚本转换旧数据
   
2. **性能影响**：真实性验证可能增加计算开销
   - 需要性能测试
   
3. **测试覆盖**：修改核心逻辑需要充分测试
   - 准备测试数据集
   - 对比修改前后结果

## 下一步

请确认：
1. 是否同意将L2A/L2B统一为L2？
2. 约束层是保留15层还是简化到3层？
3. 是否需要迁移现有的gap JSON数据？
4. 优先级顺序是否合理？
