@echo off
REM Server 3 Neo4j 连接测试脚本
REM 用于验证 Neo4j 是否正确安装和配置

echo ========================================
echo Server 3 Neo4j 连接测试
echo ========================================
echo.

REM 激活 Conda 环境
echo [1/2] 激活 Conda 环境...
call conda activate advtest
if errorlevel 1 (
    echo   X Conda 环境激活失败
    pause
    exit /b 1
)
echo   √ advtest 环境已激活
echo.

REM 测试 Neo4j 连接
echo [2/2] 测试 Neo4j 连接...
python -c "from neo4j import GraphDatabase; d = GraphDatabase.driver('bolt://127.0.0.1:7687', auth=('neo4j', '87017563')); d.verify_connectivity(); print('  √ Neo4j 连接成功!'); d.close()"

if errorlevel 1 (
    echo.
    echo ========================================
    echo X Neo4j 连接失败
    echo ========================================
    echo.
    echo 请检查:
    echo   1. Neo4j 服务是否已启动
    echo   2. 端口 7687 是否可访问
    echo   3. 密码是否为 87017563
    echo.
    echo 启动 Neo4j:
    echo   E:\neo4j-community-5.x\bin\neo4j.bat start
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo √ 测试通过，可以启动批量生产任务
echo ========================================
echo.
echo 运行以下命令启动任务:
echo   powershell -ExecutionPolicy Bypass -File start_server3_batch.ps1
echo.
pause
