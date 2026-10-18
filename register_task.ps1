<#
.SYNOPSIS
    注册 / 查看 / 立即试跑 / 删除 "每天定时发送天气到微信" 的 Windows 任务计划程序任务

.DESCRIPTION
    关键设置（都针对 wxauto4 这类界面自动化场景）：
      触发时间  : 默认读 config.py 里的 RUN_TIME，其次 08:00
      起始目录  : 项目目录（daily_send.py 自己也会 chdir，双保险）
      错过补跑  : StartWhenAvailable —— 关机/睡眠错过了时间，开机后尽快补跑
      唤醒运行  : WakeToRun —— 睡眠中到点唤醒电脑来跑（需系统允许"唤醒定时器"）
      登录类型  : Interactive —— 只在当前用户已登录时运行
                  （wxauto4 要操作微信界面，必须有交互桌面，所以不能用
                   "不管用户是否登录都运行"，否则一定会失败）

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\register_task.ps1
    powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Time 07:30
    powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -RunNow
    powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Show
    powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Remove
#>
param(
    [string]$Time,
    [string]$TaskName,
    [switch]$Pythonw,
    [switch]$RunNow,
    [switch]$Show,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$scriptFile = Join-Path $project 'daily_send.py'
$configFile = Join-Path $project 'config.py'

function Get-ConfigValue([string]$key, [string]$default) {
    if (-not (Test-Path $configFile)) { return $default }
    $match = Select-String -Path $configFile -Pattern "^\s*$key\s*=\s*'([^']*)'" | Select-Object -First 1
    if ($match) { return $match.Matches[0].Groups[1].Value }
    return $default
}

if (-not $TaskName) { $TaskName = Get-ConfigValue 'TASK_NAME' 'DailyWeatherSend' }
if (-not $Time) { $Time = Get-ConfigValue 'RUN_TIME' '08:00' }

if ($Show) {
    Write-Host "任务名称：$TaskName"
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "（没有找到该任务，先运行不带参数的本脚本进行注册）"
        exit 0
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host ("状态：{0}    上次运行：{1}    上次结果：{2}    下次运行：{3}" -f `
        $task.State, $info.LastRunTime, $info.LastTaskResult, $info.NextRunTime)
    schtasks /Query /TN $TaskName /V /FO LIST
    exit 0
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已删除计划任务：$TaskName"
    exit 0
}

# 任务计划程序里没有你的 PATH，必须用 Python 的绝对路径
$python = (& python -c "import sys; print(sys.executable)").Trim()
if ($Pythonw) { $python = $python -replace 'python\.exe$', 'pythonw.exe' }
if (-not (Test-Path $python)) { throw "找不到 Python 解释器：$python" }
if (-not (Test-Path $scriptFile)) { throw "找不到脚本：$scriptFile" }

$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}"' -f $scriptFile) -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description 'wxauto4 + 高德天气：每天定时把天气预报发到微信' | Out-Null

Write-Host "已注册计划任务"
Write-Host "   任务名称：$TaskName"
Write-Host "   执行时间：每天 $Time"
Write-Host "   执行命令：$python `"$scriptFile`""
Write-Host "   起始目录：$project"
Write-Host ""
Write-Host "常用操作："
Write-Host "   查看状态：powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Show"
Write-Host "   立即试跑：powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -RunNow"
Write-Host "   删除任务：powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Remove"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host ""
    Write-Host "已手动触发一次，几秒后看 logs\send-*.log 里的结果"
}
