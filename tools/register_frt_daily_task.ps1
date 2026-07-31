# FRT 일일 마감 — Windows 작업 스케줄러 (매일 09:00)
#
# 사용:
#   powershell -ExecutionPolicy Bypass -File tools\register_frt_daily_task.ps1
# 해제:
#   Unregister-ScheduledTask -TaskName "MisoAutomation_FRT_Daily" -Confirm:$false

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source
$TaskName = "MisoAutomation_FRT_Daily"
$Script = Join-Path $Root "tools\run_frt_daily.py"
$LogDir = Join-Path $Root "docs\frt"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Action = New-ScheduledTaskAction `
  -Execute $Python `
  -Argument "`"$Script`"" `
  -WorkingDirectory $Root

# -Daily -At 이 환경에서 null이 되는 경우 대비: 명시적 DateTime
$At = [datetime]::Today.AddHours(9)
if ($At -lt (Get-Date)) { $At = $At.AddDays(1) }
$Trigger = New-ScheduledTaskTrigger -Daily -At $At

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
Write-Host "  주기: 매일 09:00 (대상일=어제 KST)"
Write-Host "  다음 트리거 At: $At"
Write-Host "  스크립트: tools\run_frt_daily.py"
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, NextRunTime, LastTaskResult
