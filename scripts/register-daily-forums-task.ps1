# Registers the daily forum poll for the current user: every day at 09:00 while you are
# logged on (a missed run starts at next logon). It runs an hour before the Monday weekly
# task, which skips forums.
# Remove with: Unregister-ScheduledTask -TaskName 'startup-ideas-generator forums daily' -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\daily-forums.ps1'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

Register-ScheduledTask -TaskName 'startup-ideas-generator forums daily' `
    -Description 'Poll approved forum feeds; see scripts/daily-forums.ps1' `
    -Action $action -Trigger $trigger -Settings $settings -Force
