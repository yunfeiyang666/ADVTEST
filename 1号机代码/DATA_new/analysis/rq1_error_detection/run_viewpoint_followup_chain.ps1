$ErrorActionPreference = "Stop"

$ProjectRoot = "E:\Project\ADVTEST"
$ChainRoot = Join-Path $ProjectRoot "scratch\rq1_viewpoint_followup_chain_v1"
$ChainStatus = Join-Path $ChainRoot "status.json"
$FourwayStatus = Join-Path $ProjectRoot "scratch\rq1_viewpoint_4way_v1\status.json"
$NoCatchallStatus = Join-Path $ProjectRoot "scratch\rq1_viewpoint_no_catchall_v1\status.json"
$CodeRoot = (Get-ChildItem $ProjectRoot -Directory | Where-Object {
    $_.Name -like "1*"
} | Select-Object -First 1).FullName
$DataNew = Join-Path $CodeRoot "DATA_new"
$NoCatchallRunner = Join-Path $DataNew "analysis\rq1_error_detection\run_viewpoint_no_catchall_formal.ps1"
$Python = Join-Path $ProjectRoot ".venv310\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $ChainRoot | Out-Null

function Write-ChainStatus([string]$Status, [string]$Stage, [string]$Message = "") {
    @{
        status = $Status
        stage = $Stage
        message = $Message
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $ChainStatus
}

try {
    Write-ChainStatus "running" "waiting_for_fourway"
    while ($true) {
        if (-not (Test-Path $FourwayStatus)) {
            throw "Four-way status file is missing"
        }
        $Fourway = Get-Content -Raw $FourwayStatus | ConvertFrom-Json
        if ($Fourway.status -eq "completed") {
            break
        }
        if ($Fourway.status -eq "failed") {
            throw "Four-way formal evaluation failed"
        }
        Start-Sleep -Seconds 30
    }

    Write-ChainStatus "running" "running_no_catchall"
    & $NoCatchallRunner
    $NoCatchall = Get-Content -Raw $NoCatchallStatus | ConvertFrom-Json
    if ($NoCatchall.status -ne "completed") {
        throw "No-catchall formal evaluation did not complete"
    }

    Write-ChainStatus "running" "building_final_analysis"
    Push-Location $DataNew
    try {
        & $Python "analysis\rq1_error_detection\analyze_viewpoint_versions.py" `
            --strict-results "$ProjectRoot\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\advtest_l2_viewpoint_transfer_suite_raw_results.jsonl" `
            --v7-results "$ProjectRoot\scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_recover_mixed_viewpoint\advtest_l2_viewpoint_transfer_choice_suite_raw_results.jsonl" `
            --fourway-suite "$ProjectRoot\scratch\rq1_viewpoint_4way_v1\choice_suites\advtest_l2_viewpoint_transfer_4way_choice_suite.jsonl" `
            --fourway-results "$ProjectRoot\scratch\rq1_viewpoint_4way_v1\mplug_formal\advtest_l2_viewpoint_transfer_4way_choice_suite_raw_results.jsonl" `
            --no-catchall-results "$ProjectRoot\scratch\rq1_viewpoint_no_catchall_v1\mplug_formal\advtest_l2_viewpoint_transfer_6way_no_catchall_choice_suite_raw_results.jsonl" `
            --output-dir "$ProjectRoot\scratch\rq1_viewpoint_followup_chain_v1\analysis"
        if ($LASTEXITCODE -ne 0) {
            throw "Final diagnosis generation failed with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    Write-ChainStatus "completed" "done"
}
catch {
    Write-ChainStatus "failed" "error" $_.Exception.Message
    throw
}
