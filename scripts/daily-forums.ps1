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

# Extract straight away: no-retain forums (Futura-Sciences) must lose their text the same
# day. The cap keeps subscription usage modest; stage 8 tunes it.
"=== extract $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
uv run python -m pipeline extract --source forums --max-items 150 *>&1 | Out-File -Append -Encoding utf8 $log
"=== extract exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
uv run python -m pipeline scrub *>&1 | Out-File -Append -Encoding utf8 $log
