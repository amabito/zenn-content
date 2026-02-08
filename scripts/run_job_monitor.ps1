# Freelance Job Monitor - Local runner for Windows Task Scheduler
# Runs every 3 hours

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Load .env.local
$EnvFile = Join-Path $RepoRoot ".env.local"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

# Verify required env
if (-not $env:DISCORD_WEBHOOK_URL) {
    Write-Error "DISCORD_WEBHOOK_URL not set. Add it to $EnvFile"
    exit 1
}

# Run job monitor
Set-Location $RepoRoot
python "$ScriptDir\job_monitor.py"

# Commit state file if changed
$stateFile = Join-Path $RepoRoot ".job-monitor-state.json"
if (Test-Path $stateFile) {
    git -C $RepoRoot add .job-monitor-state.json
    $hasChanges = git -C $RepoRoot diff --staged --quiet 2>&1; $LASTEXITCODE -ne 0
    if ($hasChanges) {
        git -C $RepoRoot commit -m "chore: update job monitor state"
        git -C $RepoRoot push origin main
    }
}
