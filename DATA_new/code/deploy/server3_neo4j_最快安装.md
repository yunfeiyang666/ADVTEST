# Server 3 Neo4j 最快安装方式

## 下载 Windows 版本

直接下载链接（Neo4j Community 5.x）：
```
https://dist.neo4j.org/neo4j-community-5.18.0-windows.zip
```

或访问：https://neo4j.com/deployment-center/ 选择 Windows 版本

## 安装步骤（5 分钟）

### 1. 解压
解压到：`E:\neo4j`

### 2. 设置密码
打开 PowerShell（普通权限即可）：
```powershell
cd E:\neo4j
.\bin\neo4j-admin.bat dbms set-initial-password 87017563
```

### 3. 启动 Neo4j
```powershell
.\bin\neo4j.bat console
```

看到 `Started.` 就成功了，保持这个窗口运行。

### 4. 测试连接（新开一个 PowerShell）
```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\deploy
.\test_neo4j_connection.bat
```

### 5. 启动任务（新开一个 PowerShell）
```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\deploy
powershell -ExecutionPolicy Bypass -File start_server3_batch.ps1
```

## 注意
- Neo4j 窗口不要关闭，关闭就停止服务了
- 如果要后台运行，用：`.\bin\neo4j.bat start`
- 停止服务：`.\bin\neo4j.bat stop`

就这么简单！
