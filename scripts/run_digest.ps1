# Daily Tech Digest - Local runner for Windows Task Scheduler
# Weekday 08:30, Weekend/Holiday 10:00

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Holiday check: if weekday holiday, wait until 10:00
$isHoliday = python -c "import jpholiday; from datetime import date; print('1' if jpholiday.is_holiday(date.today()) else '0')" 2>$null
$isWeekday = (Get-Date).DayOfWeek -notin @('Saturday', 'Sunday')
$now = Get-Date

if ($isHoliday -eq '1' -and $isWeekday) {
    $target = (Get-Date).Date.AddHours(10)
    if ($now -lt $target) {
        $wait = ($target - $now).TotalSeconds
        Write-Host "[Digest] Holiday detected. Waiting until 10:00 ($([int]$wait)s)..."
        Start-Sleep -Seconds ([int]$wait)
    }
}

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

# Run digest with translation enabled
Set-Location $RepoRoot
python "$ScriptDir\daily_tech_digest.py"

# Commit state file if changed
$stateFile = Join-Path $RepoRoot ".digest-state.json"
if (Test-Path $stateFile) {
    git -C $RepoRoot add .digest-state.json
    $hasChanges = git -C $RepoRoot diff --staged --quiet 2>&1; $LASTEXITCODE -ne 0
    if ($hasChanges) {
        git -C $RepoRoot commit -m "chore: update digest state"
        git -C $RepoRoot push origin main
    }
}
