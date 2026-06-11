# Server 3 (Windows) Neo4j 安装指南

## 版本信息
- Neo4j Community Edition 2026.03.1
- 与 Server 1/2 保持一致

## 安装步骤

### 1. 下载 Neo4j Windows 版本

访问 Neo4j 官网下载页面：
```
https://neo4j.com/deployment-center/
```

或直接下载链接（需要确认最新版本）：
```
https://dist.neo4j.org/neo4j-community-2026.03.1-windows.zip
```

### 2. 解压到指定目录

建议解压到：
```
E:\neo4j-community-2026.03.1
```

### 3. 配置 Neo4j

编辑配置文件：`E:\neo4j-community-2026.03.1\conf\neo4j.conf`

关键配置项：
```conf
# 启用 Bolt 协议
server.bolt.enabled=true
server.bolt.listen_address=:7687

# 启用 HTTP 协议（可选，用于浏览器访问）
server.http.enabled=true
server.http.listen_address=:7474

# 设置初始密码（首次启动后需要修改）
dbms.security.auth_enabled=true

# 内存配置（根据服务器内存调整）
server.memory.heap.initial_size=2g
server.memory.heap.max_size=4g
server.memory.pagecache.size=2g
```

### 4. 设置初始密码

打开 PowerShell，进入 Neo4j 目录：
```powershell
cd E:\neo4j-community-2026.03.1
.\bin\neo4j-admin.bat dbms set-initial-password 87017563
```

### 5. 安装为 Windows 服务（推荐）

以管理员身份运行 PowerShell：
```powershell
cd E:\neo4j-community-2026.03.1
.\bin\neo4j.bat install-service
.\bin\neo4j.bat start
```

或者直接启动（不安装服务）：
```powershell
.\bin\neo4j.bat console
```

### 6. 验证安装

检查服务状态：
```powershell
.\bin\neo4j.bat status
```

测试连接：
```powershell
# 使用 cypher-shell 测试
.\bin\cypher-shell.bat -u neo4j -p 87017563
```

或在浏览器访问：
```
http://localhost:7474
```

### 7. Python 连接测试

在 Server 3 上运行：
```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\official_pipeline

# 激活环境
conda activate advtest

# 测试连接
python -c "from neo4j import GraphDatabase; d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563')); d.verify_connectivity(); print('Neo4j connected!'); d.close()"
```

## 环境变量配置

Server 3 的 `advtest_runtime_server3.env` 已配置：
```env
VQA_SKIP_NEO4J_DOCKER=true
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=87017563
VQA_BUILD_SCENE_GRAPH_ONTHEFLY=true
```

## 启动批量生产任务

安装完成后，运行：
```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\official_pipeline

# 加载环境变量并启动
powershell -ExecutionPolicy Bypass -File start_server3_batch.ps1
```

## 故障排查

### 端口被占用
```powershell
# 检查 7687 端口
netstat -ano | findstr :7687

# 如果被占用，终止进程
taskkill /PID <进程ID> /F
```

### 服务启动失败
```powershell
# 查看日志
type E:\neo4j-community-2026.03.1\logs\neo4j.log
```

### 连接被拒绝
- 检查防火墙是否阻止 7687 端口
- 确认 Neo4j 服务已启动
- 验证密码是否正确（neo4j/87017563）
