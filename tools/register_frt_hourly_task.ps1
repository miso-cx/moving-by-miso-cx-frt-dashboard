# FRT ops dashboard scheduler — every 30 minutes
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\register_frt_hourly_task.ps1
# Remove:
#   Unregister-ScheduledTask -TaskName "MisoAutomation_FRT_OpsHourly" -Confirm:$false

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source
$TaskName = "MisoAutomation_FRT_OpsHourly"
$Script = Join-Path $Root "tools\refresh_frt_ops_dashboard.py"
$LogDir = Join-Path $Root "docs\frt"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Cmd = "/c set FRT_AUTO_DEPLOY=1&& set FRT_DEPLOY_TARGET=github&& `"$Python`" `"$Script`""
$Action = New-ScheduledTaskAction `
  -Execute "cmd.exe" `
  -Argument $Cmd `
  -WorkingDirectory $Root

$Start = Get-Date
$Trigger = New-ScheduledTaskTrigger `
  -Once `
  -At $Start `
  -RepetitionInterval (New-TimeSpan -Minutes 30) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -WakeToRun `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
  -RestartCount 2 `
  -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Force | Out-Null

Write-Host "Registered: $TaskName"
Write-Host "Interval: every 30 minutes"
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, NextRunTime, LastTaskResult
