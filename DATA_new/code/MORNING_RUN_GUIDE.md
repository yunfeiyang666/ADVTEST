# 明早运行指南 - 两帧测试

## 快速启动（推荐）

### 方法1：一键运行脚本
1. 双击运行：`E:\Project\ADVTEST\DATA_new\code\run_two_frames_test.bat`
2. 等待完成（预计10-20分钟）
3. 查看结果文件

### 方法2：手动运行

#### 步骤1：启动Neo4j数据库
```bash
cd E:\Project\ADVTEST\DATA_new\code
neo4j-community-2026.03.1\bin\neo4j.bat console
```
等待看到 "Started" 提示（约30秒）

#### 步骤2：运行Frame 8测试
打开新的命令行窗口：
```bash
cd E:\Project\ADVTEST\DATA_new\code\official_pipeline
python run_gap_pipeline_v6.py --scene-name scene-0916 --frame-idx 8 --l2a-cells 50 --l2b-cells 50 --output output/scene0916_frame8_result.json --csv output/scene0916_frame8_result.csv --batch-size 16 --workers 8
```

#### 步骤3：运行Frame 10测试
```bash
python run_gap_pipeline_v6.py --scene-name scene-0916 --frame-idx 10 --l2a-cells 50 --l2b-cells 50 --output output/scene0916_frame10_result.json --csv output/scene0916_frame10_result.csv --batch-size 16 --workers 8
```

---

## 预期输出文件

### CSV结果文件（标准格式）
- `output/scene0916_frame8_result.csv` - Frame 8的100个问题
- `output/scene0916_frame10_result.csv` - Frame 10的100个问题

### JSON结果文件（详细信息）
- `output/scene0916_frame8_result.json`
- `output/scene0916_frame10_result.json`

---

## 关键检查点

### 1. Mid节点具体化效果
检查CSV中的问题是否使用具体ID：
```
正确: "Is there a truck to the front of car1 that is to the left of building1?"
错误: "Is there a truck to the front of the car that is to the left of building1?"
```

### 2. 唯一性比例
统计 `is_unique=True` 的比例：
- 预期：60-80%（修改后应该提升）
- 对比：修改前约40-60%

### 3. 逻辑验证通过率
统计 `logic_verification=True` 的比例：
- 预期：70-90%

### 4. 问题数量
- Frame 8: 100个问题（50 L2A + 50 L2B）
- Frame 10: 100个问题（50 L2A + 50 L2B）

---

## 预期运行时间

- Neo4j启动：30秒
- Frame 8生成（100题）：5-10分钟
- Frame 10生成（100题）：5-10分钟
- **总计**：约10-20分钟

---

## 今日完成的修改

### 1. Mid节点具体化（核心修改）
- 修改21个L2模板
- `{mid_type}` → `{mid_id}`
- 消除中间节点不确定性

### 2. Gap选择优化
- 优先级评分算法
- L0×10 + L1×15

### 3. 批处理优化
- 支持可配置参数
- BATCH_SIZE=16, N_WORKERS=8

---

## 明早查看重点

1. CSV文件是否生成
2. 问题中是否使用具体ID（如car1而不是car）
3. is_unique比例是否提升
4. logic_verification通过率
5. 总问题数量是否达到200个（2帧×100题）

---

## 结果文件位置

```
E:\Project\ADVTEST\DATA_new\code\official_pipeline\output\
├── scene0916_frame8_result.csv
├── scene0916_frame8_result.json
├── scene0916_frame10_result.csv
└── scene0916_frame10_result.json
```

祝测试顺利！明早见！
