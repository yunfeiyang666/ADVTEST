# Neo4j 启动指令

## 方法1: 使用已安装的 Neo4j

### 如果使用 Neo4j 5.23.0 (兼容 Java 17)
```bash
cd E:\node4j\neo4j-community-5.23.0
bin\neo4j.bat console
```

### 如果使用 Neo4j 2026.03.1 (需要 Java 21)
```bash
cd E:\Project\ADVTEST\neo4j-community-2026.03.1
bin\neo4j.bat console
```

## 方法2: 使用 Docker (如果已安装)
```bash
docker run -d \
  --name advtest-neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/87017563 \
  neo4j:5.23.0
```

## 验证 Neo4j 是否启动成功

等待看到以下提示：
```
Started.
```

然后在新的命令行窗口测试连接：
```bash
cd E:\Project\ADVTEST\DATA_new\code\official_pipeline
python -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563')); driver.verify_connectivity(); print('Neo4j connected!'); driver.close()"
```

如果看到 "Neo4j connected!"，说明启动成功。

## 启动后运行两帧测试

```bash
cd E:\Project\ADVTEST\DATA_new\code
python run_from_plan.py two_frames_plan.json
```

## 预期输出位置

成功运行后，输出文件在：
- Excel: `E:\Project\ADVTEST\DATA_new\data\RQ_nuscenesqa_val_full.xlsx`
- JSON: `E:\Project\ADVTEST\DATA_new\generated_qa\scene-0916_frame8_qa.json`
- JSON: `E:\Project\ADVTEST\DATA_new\generated_qa\scene-0916_frame10_qa.json`

## 检查输出

```bash
# 检查生成的 QA 文件
ls -lh E:\Project\ADVTEST\DATA_new\generated_qa\

# 检查 Excel 文件
ls -lh E:\Project\ADVTEST\DATA_new\data\RQ_nuscenesqa_val_full.xlsx
```
