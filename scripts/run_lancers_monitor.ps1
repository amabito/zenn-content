# Lancers Message Monitor - Local runner for Windows Task Scheduler
# Runs every 30 minutes to check for new messages/proposals
# Auth: Uses Playwright persistent context (run --setup first)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Load .env.local for Discord webhook
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

if (-not $env:DISCORD_WEBHOOK_URL) {
    Write-Error "DISCORD_WEBHOOK_URL not set. Add it to $EnvFile"
    exit 1
}

# Run message monitor (headless - uses saved Playwright session)
Set-Location $RepoRoot
python "$ScriptDir\lancers_message_monitor.py"
