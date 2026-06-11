# Server 3 快速启动指南

## 第一步：安装 Neo4j（仅首次需要）

### 方法 1：使用 Neo4j Desktop（推荐，最简单）

1. 下载 Neo4j Desktop for Windows：
   ```
   https://neo4j.com/download/
   ```

2. 安装后创建新数据库：
   - Database Name: advtest
   - Password: 87017563
   - Version: 5.x (最新稳定版)

3. 启动数据库，确保运行在 bolt://localhost:7687

### 方法 2：使用 Neo4j Community Edition（命令行）

1. 下载 Windows 版本：
   ```
   https://neo4j.com/deployment-center/
   选择：Neo4j Community Edition 5.x - Windows
   ```

2. 解压到 `E:\neo4j-community-5.x`

3. 以管理员身份打开 PowerShell，运行：
   ```powershell
   cd E:\neo4j-community-5.x
   .\bin\neo4j-admin.bat dbms set-initial-password 87017563
   .\bin\neo4j.bat install-service
   .\bin\neo4j.bat start
   ```

4. 验证安装：
   ```powershell
   .\bin\neo4j.bat status
   ```

## 第二步：测试 Neo4j 连接

在 Server 3 上运行：

```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\official_pipeline
conda activate advtest

python -c "from neo4j import GraphDatabase; d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563')); d.verify_connectivity(); print('✅ Neo4j 连接成功!'); d.close()"
```

如果看到 `✅ Neo4j 连接成功!`，说明配置正确。

## 第三步：启动批量生产任务

```powershell
cd E:\本科生万云扬实验\ADVTEST\DATA_new\code\deploy
powershell -ExecutionPolicy Bypass -File start_server3_batch.ps1
```

## 常见问题

### Q1: 端口 7687 被占用
```powershell
netstat -ano | findstr :7687
# 找到进程 ID 后终止
taskkill /PID <进程ID> /F
```

### Q2: Neo4j 服务启动失败
检查日志：
```powershell
type E:\neo4j-community-5.x\logs\neo4j.log
```

### Q3: Python 连接失败
- 确认 Neo4j 服务已启动
- 确认密码为 87017563
- 确认端口 7687 未被防火墙阻止

## 任务信息

- **Server 3 任务**：多节点帧（25-40 节点）
- **帧数**：2454 帧（已打乱）
- **计划文件**：nuscenesqa_val_plan_server3_full.json
- **输出目录**：E:\本科生万云扬实验\ADVTEST\DATA_new\csv_output\

## 监控任务进度

查看 CSV 输出：
```powershell
# 查看已生成问题数
(Get-Content E:\本科生万云扬实验\ADVTEST\DATA_new\csv_output\question_answer_our.csv).Count - 1

# 实时监控（每 10 秒刷新）
while ($true) {
    Clear-Host
    $count = (Get-Content E:\本科生万云扬实验\ADVTEST\DATA_new\csv_output\question_answer_our.csv).Count - 1
    Write-Host "已生成问题数: $count" -ForegroundColor Green
    Start-Sleep -Seconds 10
}
```
