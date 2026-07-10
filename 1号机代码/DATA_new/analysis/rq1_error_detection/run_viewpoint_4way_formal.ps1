$ErrorActionPreference = "Stop"

$ProjectRoot = "E:\Project\ADVTEST"
$RunRoot = Join-Path $ProjectRoot "scratch\rq1_viewpoint_4way_v1"
$SuiteDir = Join-Path $RunRoot "choice_suites"
$OutputDir = Join-Path $RunRoot "mplug_formal"
$LogDir = Join-Path $RunRoot "logs"
$StatusPath = Join-Path $RunRoot "status.json"
$DataNew = Join-Path $ProjectRoot "1号机代码\DATA_new"
$EvalScript = Join-Path $DataNew "analysis\rq1_error_detection\run_suite_evaluation.py"
$Python = Join-Path $ProjectRoot ".venv310\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $OutputDir, $LogDir | Out-Null
$Stdout = Join-Path $LogDir "stdout.log"
$Stderr = Join-Path $LogDir "stderr.log"

@{
    status = "running"
    started_at = (Get-Date).ToString("o")
    suite_dir = $SuiteDir
    output_dir = $OutputDir
    method = "advtest_l2_viewpoint_transfer_4way_choice"
    expected_rows = 1000
} | ConvertTo-Json | Set-Content -Encoding UTF8 $StatusPath

try {
    $Arguments = @(
        $EvalScript,
        "--suite-dir", $SuiteDir,
        "--output-dir", $OutputDir,
        "--outputs-root", (Join-Path $DataNew "outputs"),
        "--dataroot", (Join-Path $DataNew "data"),
        "--mode", "MPLUG",
        "--methods", "advtest_l2_viewpoint_transfer_4way_choice"
    )
    $Process = Start-Process -FilePath $Python -ArgumentList $Arguments `
        -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr `
        -NoNewWindow -Wait -PassThru
    if ($Process.ExitCode -ne 0) {
        throw "Formal evaluation exited with code $($Process.ExitCode)"
    }
    @{
        status = "completed"
        completed_at = (Get-Date).ToString("o")
        suite_dir = $SuiteDir
        output_dir = $OutputDir
        method = "advtest_l2_viewpoint_transfer_4way_choice"
        expected_rows = 1000
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $StatusPath
}
catch {
    @{
        status = "failed"
        failed_at = (Get-Date).ToString("o")
        message = $_.Exception.Message
        stdout = $Stdout
        stderr = $Stderr
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $StatusPath
    throw
}
