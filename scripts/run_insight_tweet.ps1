# Auto Tweet Insight - Local runner for Windows Task Scheduler
# Posts AI-generated tech insight tweets at irregular intervals

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
if (-not $env:TWITTER_API_KEY) {
    Write-Error "TWITTER_API_KEY not set. Add Twitter credentials to $EnvFile"
    exit 1
}

Set-Location $RepoRoot
python "$ScriptDir\auto_tweet_insight.py"
