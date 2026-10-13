# Daily forum poll. Forum feeds hold 15-20 threads and turn over within hours, so a
# weekly run would miss most of them. Logs to data/logs/forums-<date>.log.

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("forums-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

"=== forums $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
uv run python -m pipeline collect --only forums *>&1 | Out-File -Append -Encoding utf8 $log
"=== forums exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
