# Neo4j 下载和安装指南

## 问题
现有Neo4j需要Java 21，但系统只有Java 17

## 解决方案：下载Neo4j 5.23.0

### 方法1：浏览器下载（推荐）
1. 打开浏览器，访问：
   https://neo4j.com/deployment-center/

2. 选择：
   - Product: Neo4j Community Edition
   - Version: 5.23.0
   - OS: Windows

3. 点击下载，保存到：`E:\node4j\`

### 方法2：直接下载链接
复制以下链接到浏览器：
```
https://dist.neo4j.org/neo4j-community-5.23.0-windows.zip
```

### 方法3：使用迅雷等下载工具
下载地址：
```
https://dist.neo4j.org/neo4j-community-5.23.0-windows.zip
```
保存位置：`E:\node4j\`

## 安装步骤

### 1. 解压文件
将下载的 `neo4j-community-5.23.0-windows.zip` 解压到：
```
E:\node4j\neo4j-community-5.23.0\
```

### 2. 启动Neo4j
打开命令行，运行：
```bash
cd E:\node4j\neo4j-community-5.23.0
bin\neo4j.bat console
```

等待看到 "Started" 提示

### 3. 验证连接
打开新的命令行窗口：
```bash
cd E:\Project\ADVTEST\DATA_new\code\official_pipeline
python -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563')); driver.verify_connectivity(); print('Connected!'); driver.close()"
```

如果看到 "Connected!"，说明Neo4j启动成功

### 4. 运行两帧测试
```bash
cd E:\Project\ADVTEST\DATA_new\code
python run_two_frames_v6.py
```

## 预期文件大小
- neo4j-community-5.23.0-windows.zip: 约180MB
- 解压后: 约400MB

## 如果下载很慢
可以使用国内镜像或代理，或者明早在网络好的时候下载。

---

下载完成后，按照上述步骤安装和启动即可！
