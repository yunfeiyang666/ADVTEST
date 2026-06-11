# 两帧测试运行指南

## 问题诊断

运行 `run_two_frames_v6.py` 失败的原因：
- **Neo4j数据库是空的** - 没有场景图数据
- 需要先导入场景图数据才能运行测试

## 解决方案

使用新脚本 `prepare_and_run_two_frames.py`，它会：
1. 检查场景图文件是否存在
2. 清空Neo4j数据库
3. 导入场景图数据
4. 运行两帧测试

## 运行步骤

### 1. 确保Neo4j正在运行

```bash
# 检查Neo4j是否运行
# 应该看到 "Started" 消息
```

### 2. 运行准备和测试脚本

```bash
cd E:\Project\ADVTEST\DATA_new\code
python prepare_and_run_two_frames.py
```

## 当前状态

### 可用的场景图文件

只找到：
- `E:\Project\ADVTEST\filtered_scene_graphs\scene-0916_frame8_scene_graph.json`

**缺少**：
- `scene-0916_frame10_scene_graph.json`

### 选项

#### 选项1：只测试frame 8（推荐）

脚本会自动检测只有一个文件，只运行frame 8的测试。

```bash
python prepare_and_run_two_frames.py
```

#### 选项2：生成frame 10的场景图

需要使用场景图生成脚本（如果有的话）生成 `scene-0916_frame10_scene_graph.json`。

#### 选项3：使用其他可用的场景

可用的场景（在 `filtered_scene_graphs_official/`）：
- scene-0103 frame 0, 38
- scene-0553 frame 8
- scene-0757 frame 26
- scene-0926 frame 20
- scene-1077 frame 19

可以修改脚本测试这些场景。

## 预期输出

成功运行后会生成：
- `output/scene-0916_frame8_result.csv` - CSV格式的问答对
- `output/scene-0916_frame8_result.json` - JSON格式的问答对

CSV包含字段：
- Question_ID
- Scene_Name
- Frame_Idx
- Question
- Answer
- Template_ID
- Topology_Level
- L0_Nodes
- L1_Edges
- L2_Paths
- N_L0, N_L1, N_L2
- Constraint_Trace
- Logic_Verification
- Is_Unique
- Timestamp

## 关键验证点

运行完成后检查：

1. **Mid节点具体化**：问题中是否使用具体ID（如 "car1"）而不是类型（如 "car"）
2. **Is_Unique比例**：应该在60-80%（修改前约40-60%）
3. **问题数量**：不是固定100个，而是持续生成直到所有L0/L1/L2 gap被覆盖
4. **Logic_Verification通过率**：应该在70-90%

## 故障排除

### Neo4j连接失败
- 确保Neo4j正在运行
- 检查密码（默认尝试：87017563, neo4j, password）
- 访问 http://localhost:7474 修改密码

### 场景图文件未找到
- 检查文件是否存在于搜索目录中
- 或者生成缺失的场景图文件

### 导入失败
- 检查场景图JSON格式是否正确
- 查看错误日志了解具体问题

## 下一步

成功运行后：
1. 检查生成的CSV文件
2. 验证Mid节点具体化是否生效
3. 统计is_unique比例
4. 确认问题质量
