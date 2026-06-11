@echo off
REM 启动Neo4j数据库并运行两帧测试
REM 使用方法：双击运行此脚本

echo ========================================
echo 启动Neo4j数据库和Pipeline测试
echo ========================================
echo.

REM 1. 启动Neo4j数据库
echo [1/4] 启动Neo4j数据库...
cd /d E:\Project\ADVTEST\DATA_new\code
start "Neo4j" cmd /k "neo4j-community-2026.03.1\bin\neo4j.bat console"

REM 等待Neo4j启动
echo 等待Neo4j启动（30秒）...
timeout /t 30 /nobreak

REM 2. 运行Frame 8测试
echo.
echo [2/4] 运行Frame 8测试...
cd /d E:\Project\ADVTEST\DATA_new\code\official_pipeline
python run_gap_pipeline_v6.py --scene-name scene-0916 --frame-idx 8 --l2a-cells 50 --l2b-cells 50 --output output/scene0916_frame8_result.json --csv output/scene0916_frame8_result.csv --batch-size 16 --workers 8

if %ERRORLEVEL% NEQ 0 (
    echo Frame 8 测试失败！
    pause
    exit /b 1
)

echo Frame 8 完成！
echo.

REM 3. 运行Frame 10测试
echo [3/4] 运行Frame 10测试...
python run_gap_pipeline_v6.py --scene-name scene-0916 --frame-idx 10 --l2a-cells 50 --l2b-cells 50 --output output/scene0916_frame10_result.json --csv output/scene0916_frame10_result.csv --batch-size 16 --workers 8

if %ERRORLEVEL% NEQ 0 (
    echo Frame 10 测试失败！
    pause
    exit /b 1
)

echo Frame 10 完成！
echo.

REM 4. 生成测试报告
echo [4/4] 测试完成！
echo ========================================
echo 输出文件：
echo   Frame 8 CSV:  output/scene0916_frame8_result.csv
echo   Frame 10 CSV: output/scene0916_frame10_result.csv
echo ========================================
echo.
echo 按任意键关闭...
pause
