# Registers the daily forum poll for the current user: every day at 09:00 while you are
# logged on (a missed run starts at next logon). It runs an hour before the Monday weekly
# task, which skips forums.
# Remove with: Unregister-ScheduledTask -TaskName 'startup-ideas-generator forums daily' -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\daily-forums.ps1'

# conhost --headless runs PowerShell with no console window. A visible window can be closed
# (exit 0xC000013A), which killed the 14, 19, and 21 October runs midway.
$action = New-ScheduledTaskAction -Execute 'conhost.exe' `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
# New-ScheduledTaskTrigger stores the start time as UTC ('07:00Z'), so the task follows UTC and
# would run at 8:00 local after daylight saving ends on 25 October. A boundary without an
# offset means local time.
$trigger.StartBoundary = [datetime]::Today.AddHours(9).ToString('yyyy-MM-ddTHH:mm:ss')
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

Register-ScheduledTask -TaskName 'startup-ideas-generator forums daily' `
    -Description 'Poll approved forum feeds; see scripts/daily-forums.ps1' `
    -Action $action -Trigger $trigger -Settings $settings -Force
