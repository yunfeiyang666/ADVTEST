# Server 3 批量生产启动脚本
# 任务：Server 3 (多节点帧，2454 帧，已打乱)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Server 3 批量生产任务启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Neo4j 服务
Write-Host "[1/5] 检查 Neo4j 服务..." -ForegroundColor Yellow
$neo4jRunning = $false
try {
    $service = Get-Service -Name "neo4j" -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq "Running") {
        Write-Host "  ✅ Neo4j 服务运行中" -ForegroundColor Green
        $neo4jRunning = $true
    }
} catch {}

if (-not $neo4jRunning) {
    Write-Host "  ⚠️  Neo4j 服务未运行，尝试启动..." -ForegroundColor Yellow
    try {
        & "E:\neo4j-community-2026.03.1\bin\neo4j.bat" start
        Start-Sleep -Seconds 10
        Write-Host "  ✅ Neo4j 已启动" -ForegroundColor Green
    } catch {
        Write-Host "  ❌ Neo4j 启动失败，请手动启动" -ForegroundColor Red
        Write-Host "     运行: E:\neo4j-community-2026.03.1\bin\neo4j.bat console" -ForegroundColor Red
        exit 1
    }
}

# 2. 切换到工作目录
Write-Host ""
Write-Host "[2/5] 切换工作目录..." -ForegroundColor Yellow
$workDir = "E:\本科生万云扬实验\ADVTEST\DATA_new\code\official_pipeline"
Set-Location $workDir
Write-Host "  ✅ 当前目录: $workDir" -ForegroundColor Green

# 3. 激活 Conda 环境
Write-Host ""
Write-Host "[3/5] 激活 Conda 环境..." -ForegroundColor Yellow
& conda activate advtest
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ Conda 环境激活失败" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ advtest 环境已激活" -ForegroundColor Green

# 4. 加载环境变量
Write-Host ""
Write-Host "[4/5] 加载环境变量..." -ForegroundColor Yellow
Get-Content "advtest_runtime_server3.env" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $name = $matches[1]
        $value = $matches[2]
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
        Write-Host "  $name=$value" -ForegroundColor Gray
    }
}
Write-Host "  ✅ 环境变量已加载" -ForegroundColor Green

# 5. 启动批量生产
Write-Host ""
Write-Host "[5/5] 启动批量生产任务..." -ForegroundColor Yellow
Write-Host "  任务: Server 3 (多节点帧)" -ForegroundColor Cyan
Write-Host "  帧数: 2454 帧 (已打乱)" -ForegroundColor Cyan
Write-Host "  计划文件: nuscenesqa_val_plan_server3_full.json" -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "开始执行..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 执行 Python 脚本
python run_method_a.py

# 检查退出码
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✅ 任务完成" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "❌ 任务失败 (退出码: $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    exit $LASTEXITCODE
}
