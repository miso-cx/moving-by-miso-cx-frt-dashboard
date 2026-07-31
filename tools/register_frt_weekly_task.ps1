# FRT 위클리 리포트 — Windows 작업 스케줄러 (매주 목요일 09:10)
#
# 사용:
#   powershell -ExecutionPolicy Bypass -File tools\register_frt_weekly_task.ps1
# 해제:
#   Unregister-ScheduledTask -TaskName "MisoAutomation_FRT_Weekly" -Confirm:$false

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source
$TaskName = "MisoAutomation_FRT_Weekly"
$Script = Join-Path $Root "tools\build_frt_weekly.py"

$Action = New-ScheduledTaskAction `
  -Execute $Python `
  -Argument "`"$Script`"" `
  -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At "09:10"

$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Force | Out-Null

Write-Host "등록 완료: $TaskName"
Write-Host "  주기: 매주 목요일 09:10"
Write-Host "  스크립트: tools\build_frt_weekly.py"
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, NextRunTime, LastTaskResult
