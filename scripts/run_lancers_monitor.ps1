# Lancers Message Monitor - Local runner for Windows Task Scheduler
# Runs every 30 minutes to check for new messages/proposals

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
if (-not $env:LANCERS_EMAIL -or $env:LANCERS_EMAIL -eq "YOUR_EMAIL_HERE") {
    Write-Error "LANCERS_EMAIL not set. Add it to $EnvFile"
    exit 1
}
if (-not $env:LANCERS_PASSWORD -or $env:LANCERS_PASSWORD -eq "YOUR_PASSWORD_HERE") {
    Write-Error "LANCERS_PASSWORD not set. Add it to $EnvFile"
    exit 1
}
if (-not $env:DISCORD_WEBHOOK_URL) {
    Write-Error "DISCORD_WEBHOOK_URL not set. Add it to $EnvFile"
    exit 1
}

# Run message monitor
Set-Location $RepoRoot
python "$ScriptDir\lancers_message_monitor.py"
