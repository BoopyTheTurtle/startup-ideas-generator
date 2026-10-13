# Registers the weekly run with Windows Task Scheduler for the current user.
# Runs Mondays at 10:00 while you are logged on; a missed run starts at next logon.
# Remove with: Unregister-ScheduledTask -TaskName 'startup-ideas-generator weekly' -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\weekly.ps1'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName 'startup-ideas-generator weekly' `
    -Description 'Collect problem signals; see scripts/weekly.ps1' `
    -Action $action -Trigger $trigger -Settings $settings -Force
