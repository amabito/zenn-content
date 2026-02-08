# Freelance Pipeline - Local runner for Windows Task Scheduler
# Runs every 3 hours (offset 30 min from JobMonitor: 09:30, 12:30, 15:30, ...)

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

# Run freelance pipeline scan
Set-Location $RepoRoot
python "$ScriptDir\freelance_pipeline.py" scan

# Commit state file if changed
$stateFile = Join-Path $RepoRoot ".freelance-pipeline-state.json"
if (Test-Path $stateFile) {
    git -C $RepoRoot add .freelance-pipeline-state.json
    git -C $RepoRoot diff --staged --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        git -C $RepoRoot commit -m "chore: update freelance pipeline state"
        git -C $RepoRoot push origin main
    }
}
