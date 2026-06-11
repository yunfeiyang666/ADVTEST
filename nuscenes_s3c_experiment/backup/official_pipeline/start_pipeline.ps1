<#
.SYNOPSIS
    NuScenes VQA Gap-Coverage Pipeline 启动脚本

.DESCRIPTION
    一键完成：Neo4j 健康检查 → 激活虚拟环境 → 启动问题生成器
    所有预算参数集中在文件顶部，修改后直接运行。

.USAGE
    # 前台运行（看实时日志）
    .\start_pipeline.ps1

    # 后台运行（挂后台，结果写入日志文件）
    .\start_pipeline.ps1 -Background

    # 指定预算（直接传参）
    .\start_pipeline.ps1 -MaxCells 50 -TargetCoverage 20.0 -ChainMode cumulative

    # 只跑特定场景/帧
    .\start_pipeline.ps1 -SceneName "scene-0553" -FrameIdx 8
#>

# ============================================================
#  参数声明（命令行传入会覆盖下面的默认值）
# ============================================================
param(
    # ── 预算控制 ─────────────────────────────────────────────
    [int]   $MaxCells     = 50,       # 最多处理的 gap cell 数。0 = 不限
    [int]   $MaxQA        = 0,        # 目标 QA 对总数上限。0 = 不限
    [double]$TargetCoverage = 20.0,   # 目标 edge 覆盖率 %，到达后停止。0 = 不限
    [int]   $MaxPerCell   = 1,        # 每个 gap cell 最多生成的模板 QA 对数

    # ── 约束链模式 ─────────────────────────────────────────
    # "cumulative" 动态叠加（推荐，找最小约束组合）
    # "fixed"      固定优先级链（P1-P15，速度更快）
    # "none"       只走模板，不做约束收束
    [ValidateSet("cumulative","fixed","none")]
    [string]$ChainMode    = "cumulative",

    # ── 场景过滤 ─────────────────────────────────────────
    [string]$SceneName    = "scene-0553",
    [int]   $FrameIdx     = 8,

    # ── 日志 & 输出 ──────────────────────────────────────────
    [string]$OutputDir    = "",       # 空 = 自动生成带时间戳的目录
    [switch]$Background,             # 后台运行，不阻塞当前窗口
    [switch]$SkipNeo4jCheck          # 跳过 Neo4j 健康检查（已确认在线时可用）
)

# ============================================================
#  固定路径（通常不需要改）
# ============================================================
$PIPELINE_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON       = "E:\Project\ADVTEST\.venv310\Scripts\python.exe"
$SCRIPT       = Join-Path $PIPELINE_DIR "run_gap_pipeline.py"
$NEO4J_URI    = "bolt://localhost:7800"
$NEO4J_USER   = "neo4j"
$NEO4J_PASS   = "87017563"
$NEO4J_HOME   = "E:\node4j\neo4j-community-2025.10.1"
$TIMING_LOG   = Join-Path $PIPELINE_DIR "output\timing_log.jsonl"

# ============================================================
#  工具函数
# ============================================================
function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  [$([datetime]::Now.ToString('HH:mm:ss'))]  $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "  ✓  $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  ⚠  $msg" -ForegroundColor Yellow
}

function Write-Fail([string]$msg) {
    Write-Host "  ✗  $msg" -ForegroundColor Red
}

# ============================================================
#  Step 0  打印本次参数概览
# ============================================================
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host "  NuScenes Gap-Coverage Pipeline" -ForegroundColor Magenta
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host ""
Write-Host "  预算参数" -ForegroundColor White
Write-Host "    MaxCells      = $(if($MaxCells -eq 0){'不限'}else{$MaxCells})" -ForegroundColor Gray
Write-Host "    MaxQA         = $(if($MaxQA -eq 0){'不限'}else{$MaxQA})" -ForegroundColor Gray
Write-Host "    TargetCoverage= $(if($TargetCoverage -eq 0){'不限'}else{"$TargetCoverage %"})" -ForegroundColor Gray
Write-Host "    MaxPerCell    = $MaxPerCell" -ForegroundColor Gray
Write-Host "  约束链模式      = $ChainMode" -ForegroundColor White
if ($SceneName) {
Write-Host "  场景过滤        = $SceneName  frame=$FrameIdx" -ForegroundColor White
} else {
Write-Host "  场景过滤        = 不限（全量）" -ForegroundColor White
}
Write-Host "  运行模式        = $(if($Background){'后台'}else{'前台'})" -ForegroundColor White
Write-Host ""

# ============================================================
#  Step 1  Neo4j 健康检查
# ============================================================
if (-not $SkipNeo4jCheck) {
    Write-Step "检查 Neo4j 服务..."

    $svc = Get-Service -Name "neo4j" -ErrorAction SilentlyContinue
    if ($null -eq $svc) {
        Write-Fail "找不到 neo4j 服务。请检查 Neo4j 安装路径：$NEO4J_HOME"
        exit 1
    }

    if ($svc.Status -ne "Running") {
        Write-Warn "Neo4j 服务未运行（状态：$($svc.Status)），正在启动..."
        Start-Service neo4j
        $timeout = 30
        $elapsed = 0
        while ((Get-Service neo4j).Status -ne "Running" -and $elapsed -lt $timeout) {
            Start-Sleep 2
            $elapsed += 2
            Write-Host "    等待 Neo4j 启动... ${elapsed}s" -ForegroundColor DarkGray
        }
        if ((Get-Service neo4j).Status -ne "Running") {
            Write-Fail "Neo4j 启动超时（${timeout}s），请手动检查。"
            exit 1
        }
    }
    Write-OK "Neo4j 服务运行中（$NEO4J_URI）"

    # 等待 Bolt 端口就绪
    $port = 7800
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $tcp = New-Object Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $port)
            $tcp.Close()
            $ready = $true
            break
        } catch {
            Start-Sleep 2
        }
    }
    if (-not $ready) {
        Write-Warn "Bolt 端口 $port 暂时无法连接，可能仍在初始化（继续运行）..."
    } else {
        Write-OK "Bolt 端口 $port 可连接"
    }
}

# ============================================================
#  Step 2  准备输出路径
# ============================================================
$ts = [datetime]::Now.ToString("yyyyMMdd_HHmmss")
if (-not $OutputDir) {
    $OutputDir = Join-Path $PIPELINE_DIR "output\run_$ts"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$jsonOut   = Join-Path $OutputDir "gap_result.json"
$logOut    = Join-Path $OutputDir "pipeline.log"
$logErr    = Join-Path $OutputDir "pipeline_err.log"

Write-Step "输出目录"
Write-OK   "  $OutputDir"

# ============================================================
#  Step 3  构建 Python 参数列表
# ============================================================
$pyArgs = @(
    $SCRIPT,
    "--neo4j-uri",      $NEO4J_URI,
    "--neo4j-user",     $NEO4J_USER,
    "--neo4j-password", $NEO4J_PASS,
    "--max-per-cell",   $MaxPerCell,
    "--output",         $jsonOut,
    "--timing-log",     $TIMING_LOG
)

if ($MaxCells -gt 0)         { $pyArgs += "--max-cells",        $MaxCells }
if ($MaxQA -gt 0)            { $pyArgs += "--max-qa",           $MaxQA }
if ($TargetCoverage -gt 0)   { $pyArgs += "--target-coverage",  $TargetCoverage }
if ($SceneName)              { $pyArgs += "--scene-name",       $SceneName
                               $pyArgs += "--frame-idx",        $FrameIdx }
switch ($ChainMode) {
    "cumulative" { $pyArgs += "--use-cumulative-chain" }
    "fixed"      { $pyArgs += "--use-constraint-chain" }
    # "none" 不加任何 chain 参数
}

Write-Step "Python 命令"
Write-Host "  $PYTHON $($pyArgs -join ' ')" -ForegroundColor DarkGray

# ============================================================
#  Step 4  启动（前台 / 后台）
# ============================================================
if ($Background) {
    Write-Step "后台启动..."
    $proc = Start-Process `
        -FilePath         $PYTHON `
        -ArgumentList     $pyArgs `
        -RedirectStandardOutput  $logOut `
        -RedirectStandardError   $logErr `
        -WindowStyle      Hidden `
        -PassThru
    Write-OK "进程 PID = $($proc.Id)"
    Write-Host ""
    Write-Host "  实时查看日志：" -ForegroundColor White
    Write-Host "    Get-Content '$logErr' -Wait -Tail 30" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  查看结果（完成后）：" -ForegroundColor White
    Write-Host "    \$j = Get-Content '$jsonOut' | ConvertFrom-Json" -ForegroundColor Gray
    Write-Host "    \$j.coverage" -ForegroundColor Gray
    Write-Host "    \$j.n_qa_generated" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  停止运行：" -ForegroundColor White
    Write-Host "    Stop-Process -Id $($proc.Id) -Force" -ForegroundColor Gray
    Write-Host ""

} else {
    Write-Step "前台启动（Ctrl+C 可中断）..."
    Write-Host ""
    & $PYTHON @pyArgs

    # ── 完成后显示摘要 ──
    if (Test-Path $jsonOut) {
        Write-Host ""
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
        Write-Host "  运行结果摘要" -ForegroundColor Magenta
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
        try {
            $j = Get-Content $jsonOut | ConvertFrom-Json
            Write-Host "  gap cells 处理数 : $($j.n_gap_cells)" -ForegroundColor White
            Write-Host "  QA 对生成总数    : $($j.n_qa_generated)" -ForegroundColor White
            Write-Host "  LLM 实际调用     : $($j.step5a_llm_calls)" -ForegroundColor White
            Write-Host "  LLM fallback     : $($j.step5a_fallback_calls)" -ForegroundColor White
            $cov = $j.coverage.edge
            Write-Host "  边覆盖率         : $($cov.covered) / $($cov.total) = $($cov.rate) %" -ForegroundColor White
            # 方法分布 top-5
            $topMethods = $j.cell_timings |
                Group-Object method_used |
                Sort-Object Count -Descending |
                Select-Object -First 5
            Write-Host ""
            Write-Host "  约束方法命中 top-5:" -ForegroundColor White
            foreach ($m in $topMethods) {
                Write-Host "    $($m.Name.PadRight(35)) $($m.Count.ToString().PadLeft(4)) 次" -ForegroundColor Gray
            }
        } catch {
            Write-Warn "摘要解析失败：$_"
        }
        Write-Host ""
        Write-Host "  结果文件 : $jsonOut" -ForegroundColor DarkGray
        Write-Host "  计时日志 : $TIMING_LOG" -ForegroundColor DarkGray
        Write-Host ""
    }
}
