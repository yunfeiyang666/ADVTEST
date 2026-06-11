@echo off
REM V19 Server 3 (Windows) 批量生产启动脚本
REM 大节点帧（25-40节点），共600帧

echo ==========================================
echo V19 Production - Server 3 (Windows)
echo ==========================================
echo.

cd /d E:\本科生万云扬实验\ADVTEST\DATA_new\code\official_pipeline

REM 备份当前配置
if exist advtest_runtime.env (
    copy /Y advtest_runtime.env advtest_runtime.env.bak >nul
)

REM 使用 Server 3 配置
copy /Y advtest_runtime_server3.env advtest_runtime.env >nul
echo [OK] Using Server 3 configuration
echo.

REM 检查 Neo4j
echo [Check] Neo4j status...
neo4j status >nul 2>&1
if errorlevel 1 (
    echo [WARN] Neo4j not running, attempting to start...
    neo4j start
    timeout /t 5 /nobreak >nul
)
echo.

REM 启动生产
echo ==========================================
echo Starting V19 Production
echo ==========================================
echo   Frames: 600 (large nodes, 25-40 nodes)
echo   Plan: nuscenesqa_val_plan_server3.json
echo   Log: E:\本科生万云扬实验\ADVTEST\DATA_new\v19_server3.log
echo   CSV: E:\本科生万云扬实验\ADVTEST\DATA_new\csv_output\
echo.
echo Starting in 3 seconds...
timeout /t 3 /nobreak >nul

start /B python -u run_v17_production.py > E:\本科生万云扬实验\ADVTEST\DATA_new\v19_server3.log 2>&1

echo.
echo ==========================================
echo V19 Server 3 Started
echo ==========================================
echo.
echo Monitor log:
echo   type E:\本科生万云扬实验\ADVTEST\DATA_new\v19_server3.log
echo.
echo Or use PowerShell:
echo   Get-Content E:\本科生万云扬实验\ADVTEST\DATA_new\v19_server3.log -Wait -Tail 50
echo.
echo ==========================================
