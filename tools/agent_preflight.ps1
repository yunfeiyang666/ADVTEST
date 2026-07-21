param(
    [string]$RunRoot = "E:\Project\ADVTEST\scratch\rq2_random_budget_matched\formal-s42-v1"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
    catch { return @{ parse_error = $_.Exception.Message } }
}

$statusPath = Join-Path $RunRoot "status.json"
$status = Read-JsonOrNull $statusPath
$runnerProcesses = @(
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(\.exe)?$' -and
        $_.CommandLine -match 'run_random_budget_matched_experiment\.py'
    } | ForEach-Object {
        [ordered]@{
            pid = $_.ProcessId
            created = $_.CreationDate
            command = $_.CommandLine
        }
    }
)

$payload = [ordered]@{
    audited_at = (Get-Date).ToString("o")
    repo_root = $repoRoot
    branch = (git branch --show-current).Trim()
    head = (git rev-parse --short HEAD).Trim()
    dirty_paths = @((git status --short) | Where-Object { $_ })
    random_status_path = $statusPath
    random_status = $status
    matching_random_processes = $runnerProcesses
    random_status_is_stale = [bool](
        $status -and $status.state -eq 'running' -and $runnerProcesses.Count -eq 0
    )
    required_reading = @("CLAUDE.md", "EXPERIMENT_STATE.md")
}

$payload | ConvertTo-Json -Depth 8
