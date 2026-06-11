<# ═══════════════════════════════════════════════════════════════
   ADVTEST VQA Pipeline — 两阶段批量执行脚本 (PowerShell/本机)
   用法: powershell -ExecutionPolicy Bypass -File run_batch_local.ps1 plans\plan_A_local.json
═══════════════════════════════════════════════════════════════ #>
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$PlanFile
)

# ═══════════════ 配置区 ════════════════════════════════════

$PIPELINE_ROOT = "E:\Project\ADVTEST\DATA_new\code\official_pipeline"
$OUTPUT_ROOT = Join-Path $PIPELINE_ROOT "outputs"
$CONCURRENCY = 4

# ═══════════════ 初始化 ════════════════════════════════════

Set-Location $PIPELINE_ROOT

$planData = Get-Content $PlanFile -Raw -Encoding UTF8 | ConvertFrom-Json
$total = if ($planData.frame_count) { $planData.frame_count } else { $planData.frames.Count }

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $OUTPUT_ROOT "batch_$timestamp.log"
New-Item -ItemType Directory -Force -Path $OUTPUT_ROOT | Out-Null

function Log([string]$msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " ADVTEST VQA Pipeline"
Write-Host " Plan:   $PlanFile"
Write-Host " Frames: $total"
Write-Host " Output: $OUTPUT_ROOT"
Write-Host " Time:   $(Get-Date)"
Write-Host "==================================================" -ForegroundColor Cyan

# ═══════════════ 阶段1: 离线处理 ═══════════════════════════

Write-Host ""
Write-Host "===  PHASE 1: OFFLINE (scene_graph + initial_cov)  ===" -ForegroundColor Yellow

$offlineOk = 0
$offlineFail = 0
$phase1Start = Get-Date

for ($i = 0; $i -lt $total; $i++) {
    $f = $planData.frames[$i]
    $frameInfo = "$($f.scene_id)_frame$($f.frame_id)"
    Log "OFFLINE $($i+1)/$total : $frameInfo"

    # 1a. prepare_scene_graph
    & python run_gap_pipeline_v7.py --plan prepare_scene_graph --artifact-root $OUTPUT_ROOT --plan-file $PlanFile --frame-index $i 2>&1 | Tee-Object -FilePath $logFile -Append

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR OFFLINE scene_graph $frameInfo FAILED"
        $offlineFail++
        continue
    }

    # 1b. prepare_initial_coverage
    & python run_gap_pipeline_v7.py --plan prepare_initial_coverage --artifact-root $OUTPUT_ROOT --plan-file $PlanFile --frame-index $i --concurrency $CONCURRENCY 2>&1 | Tee-Object -FilePath $logFile -Append

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR OFFLINE initial_coverage $frameInfo FAILED"
        $offlineFail++
        continue
    }

    $offlineOk++
}

$phase1Time = (Get-Date) - $phase1Start
Log ("Phase 1 DONE: OK=$offlineOk FAIL=$offlineFail Time=" + $phase1Time.ToString('hh\:mm\:ss'))

# ═══════════════ 阶段2: 在线生成 ═══════════════════════════

Write-Host ""
Write-Host "===  PHASE 2: GENERATE (gap coverage questions)  ===" -ForegroundColor Green

$genOk = 0
$genFail = 0
$phase2Start = Get-Date

for ($i = 0; $i -lt $total; $i++) {
    $f = $planData.frames[$i]
    $frameInfo = "$($f.scene_id)_frame$($f.frame_id)"

    $elapsed = (Get-Date) - $phase2Start
    if ($i -gt 0) {
        $rateVal = [math]::Round($elapsed.TotalSeconds / $i, 1)
        $etaVal = [math]::Round(($total - $i) * $elapsed.TotalMinutes / $i, 1)
        $progressStr = "${rateVal}s/frame, ETA ${etaVal}min"
    } else {
        $progressStr = "starting"
    }

    Log "GENERATE $($i+1)/$total : $frameInfo ($progressStr)"

    & python run_gap_pipeline_v7.py --plan generate --artifact-root $OUTPUT_ROOT --plan-file $PlanFile --frame-index $i 2>&1 | Tee-Object -FilePath $logFile -Append

    if ($LASTEXITCODE -ne 0) {
        Log "ERROR GENERATE $frameInfo FAILED"
        $genFail++
    } else {
        $genOk++
    }
}

$phase2Time = (Get-Date) - $phase2Start
$totalTime = $phase1Time + $phase2Time

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " BATCH COMPLETE"
Write-Host (" Phase 1 (Offline):  OK=$offlineOk FAIL=$offlineFail Time=" + $phase1Time.ToString('hh\:mm\:ss'))
Write-Host (" Phase 2 (Generate): OK=$genOk FAIL=$genFail Time=" + $phase2Time.ToString('hh\:mm\:ss'))
Write-Host (" Total: " + $totalTime.ToString('hh\:mm\:ss'))
Write-Host " Log: $logFile"
Write-Host "==================================================" -ForegroundColor Cyan

if ($offlineFail -gt 0 -or $genFail -gt 0) {
    Write-Host "Errors logged to $(Join-Path $OUTPUT_ROOT 'errors.log')" -ForegroundColor Red
}
