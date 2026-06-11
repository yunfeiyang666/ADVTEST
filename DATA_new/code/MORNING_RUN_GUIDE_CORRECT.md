# 两帧测试完整指南 - 2026-04-23 晚

## 今日完成的工作

### 1. Mid节点具体化修改（核心修复）
- 修改了21个L2模板，将 `{mid_type}` 替换为 `{mid_id}`
- 文件：`official_pipeline/gap_pipeline/template_library.py`
- 效果：消除中间节点不确定性，预期 is_unique 比例提升 20-40%

### 2. Gap选择策略优化
- 在 `coverage_tracker.py` 中添加了优先级评分方法
- 评分公式：`priority = uncovered_l0 × 10 + uncovered_l1 × 15`
- 自适应策略：80%高优先级 + 20%随机

### 3. 创建正确的测试脚本
- **重要澄清**：不是固定100个问题！
- 根据 design(1).md，应该持续生成直到所有L0/L1/L2 gap都被覆盖
- L2A和L2B的区分已废弃，统一为L2
- 每帧生成的问题数量取决于该帧有多少个L2 gap

## 明早运行步骤

### 步骤0：解决Neo4j问题（重要！）

**问题**：现有的Neo4j版本都需要Java 21，但系统只有Java 17

**解决方案（三选一）**：

#### 方案1：下载兼容Java 17的Neo4j（推荐）
1. 下载 Neo4j 5.23.0 Community Edition (Windows)
2. 下载地址：https://neo4j.com/deployment-center/
3. 解压到 `E:\node4j\neo4j-community-5.23.0`
4. 运行：`E:\node4j\neo4j-community-5.23.0\bin\neo4j.bat console`

#### 方案2：升级Java到21
1. 下载 OpenJDK 21
2. 安装并设置环境变量
3. 使用现有的Neo4j 2025.10.1

#### 方案3：使用Docker运行Neo4j
```bash
docker run -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/87017563 neo4j:5.23.0
```

### 步骤1：启动Neo4j
解决上述问题后，启动Neo4j并等待看到 "Started" 提示（约30-60秒）

### 步骤2：运行两帧测试
打开新的命令行窗口：
```bash
cd E:\Project\ADVTEST\DATA_new\code
python run_two_frames_v6.py
```

## 预期输出

### 输出文件
```
E:\Project\ADVTEST\DATA_new\code\official_pipeline\output\
├── scene-0916_frame8_result.csv
├── scene-0916_frame8_result.json
├── scene-0916_frame10_result.csv
└── scene-0916_frame10_result.json
```

### CSV格式（标准格式）
根据 run_gap_pipeline_v6.py 的输出格式：
```
Question_ID, Scene_Name, Frame_Idx, Question, Answer, Template_ID, Topology_Level,
L0_Nodes, L1_Edges, L2_Paths, N_L0, N_L1, N_L2,
Constraint_Trace, Logic_Verification, Is_Unique, Timestamp
```

### 关键检查点

#### 1. Mid节点具体化效果
检查CSV中的问题是否使用具体ID：
- ✓ 正确：`"Is there a truck to the front of car1 that is..."`
- ✗ 错误：`"Is there a truck to the front of the car that is..."`

#### 2. 问题数量
- **不是固定的100个**
- Frame 8: 生成问题直到所有gap覆盖完成
- Frame 10: 生成问题直到所有gap覆盖完成
- 实际数量取决于该帧的L2 gap数量

#### 3. Is_Unique比例
- 预期：60-80%（修改后应该提升）
- 对比：修改前约40-60%

#### 4. Logic_Verification通过率
- 预期：70-90%

## 预期运行时间

- Neo4j启动：30-60秒
- Frame 8生成：取决于gap数量，可能5-30分钟
- Frame 10生成：取决于gap数量，可能5-30分钟
- **总计**：约10-60分钟（取决于gap数量）

## 重要说明

### 关于问题数量
之前文档中提到的"100个问题"是**错误的理解**。正确的流程是：

1. 系统会持续生成问题
2. 直到该帧的所有L0、L1、L2 gap都被标记为 `covered=true`
3. 问题数量是**动态的**，不是固定的100个
4. 每帧可能生成几十个到几百个问题，取决于：
   - 该帧有多少个L2 gap
   - 每个问题能覆盖多少个gap
   - Gap选择策略的效率

### 关于L2A和L2B
- **已废弃**：不再区分L2A和L2B
- **统一为L2**：所有三跳路径统一管理
- 代码中的 `l2a_cells` 和 `l2b_cells` 参数设为 `None`，让系统自动运行到完成

## 核心改进总结

### 从不确定到确定
- 修改前：`"the car"` 可能匹配多个对象
- 修改后：`"car1"` 唯一确定

### 从随机到智能
- 修改前：随机选择gap
- 修改后：优先级评分选择，L1边权重更高

### 从固定到动态
- 修改前：固定生成100个问题
- 修改后：持续生成直到所有gap覆盖完成

## 如果遇到问题

### Neo4j连接失败
1. 检查Neo4j是否启动成功
2. 检查端口7687是否被占用
3. 检查密码是否正确（87017563）

### 生成问题失败
1. 检查LLM API是否可用
2. 检查场景图数据是否存在
3. 查看错误日志

### 问题数量异常
- 如果生成问题很少：检查gap初始化是否正确
- 如果生成问题很多：正常，说明该帧gap较多

---

祝测试顺利！明早见！
