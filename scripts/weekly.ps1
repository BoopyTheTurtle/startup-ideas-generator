# Weekly pipeline run. Task Scheduler calls this; it is also safe to run by hand.
# Each step logs to data/logs/weekly-<date>.log. Later phases append steps here
# (extract, map, headless Claude, reassess).

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("weekly-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

function Step($name, [scriptblock]$body) {
    "=== $name $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
    & $body *>&1 | Out-File -Append -Encoding utf8 $log
    "=== $name exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
}

# Forums poll daily (scripts/daily-forums.ps1); skipping them here avoids two runs at once.
Step 'collect' { uv run python -m pipeline collect --skip forums }
# Capped to keep subscription usage modest (~$0.01 of API-equivalent per item); stage 8 tunes it.
Step 'extract' { uv run python -m pipeline extract --max-items 600 }
Step 'scrub'   { uv run python -m pipeline scrub }
Step 'health'  { uv run python -m pipeline health }
