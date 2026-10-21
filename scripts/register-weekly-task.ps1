# Registers the weekly run with Windows Task Scheduler for the current user.
# Runs Mondays at 10:00 while you are logged on; a missed run starts at next logon.
# Remove with: Unregister-ScheduledTask -TaskName 'startup-ideas-generator weekly' -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\weekly.ps1'

# conhost --headless runs PowerShell with no console window. A visible window can be closed
# (exit 0xC000013A), which killed the 14, 19, and 21 October runs midway.
$action = New-ScheduledTaskAction -Execute 'conhost.exe' `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10am
# New-ScheduledTaskTrigger stores the start time as UTC ('07:00Z'), so the task follows UTC and
# would run at 9:00 local after daylight saving ends on 25 October. A boundary without an
# offset means local time.
$trigger.StartBoundary = [datetime]::Today.AddHours(10).ToString('yyyy-MM-ddTHH:mm:ss')
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName 'startup-ideas-generator weekly' `
    -Description 'Collect problem signals; see scripts/weekly.ps1' `
    -Action $action -Trigger $trigger -Settings $settings -Force
