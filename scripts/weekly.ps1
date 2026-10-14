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
# Once the embedding model is cached, stay offline so a Hub outage can't stop the weekly
# run. Before the first download, leave the Hub reachable so map can fetch the model.
$hfHome = if ($env:HF_HOME) { $env:HF_HOME } else { Join-Path $env:USERPROFILE '.cache\huggingface' }
$hfHub = if ($env:HF_HUB_CACHE) { $env:HF_HUB_CACHE } else { Join-Path $hfHome 'hub' }
if (Test-Path (Join-Path $hfHub 'models--intfloat--multilingual-e5-small')) {
    $env:HF_HUB_OFFLINE = '1'
}
Step 'map'     { uv run python -m pipeline map }
# Themes after map (pains already embedded) and before curate; names new themes with Sonnet (<= 40).
Step 'themes'  { uv run python -m pipeline themes }
Step 'curate'  { uv run python -m pipeline curate }
Step 'health'  { uv run python -m pipeline health }
# Stage 8: metrics, mutation tests, revert and instrument cards, digest. No LLM calls.
# The auditor (LLM, on Edgar's subscription) proposes cards from the digest. Off until Edgar
# sets SIG_HEADLESS_AUDIT=1 for the scheduled task; /reassess then runs reassess itself.
if ($env:SIG_HEADLESS_AUDIT -ne '1') {
    Step 'reassess' { uv run python -m pipeline reassess }
} else {
    Step 'audit' { claude -p "/reassess" --allowedTools "Agent" "Read" "Grep" "Glob" "Bash(uv run python -m pipeline reassess*)" "Bash(uv run python -m pipeline digest*)" "Bash(uv run python -m pipeline cards*)" "Bash(uv run python -m pipeline card-show*)" "Bash(uv run python -m pipeline card-add*)" }
}
