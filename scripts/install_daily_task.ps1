param(
    [string]$TaskName = "RealEstateBrokerDatabaseDaily",
    [string]$RunAt = "09:00"
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
$Runner = Join-Path $RootDir "scripts\run_daily.py"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python. Create .venv and install dependencies first."
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $Runner) -WorkingDirectory $RootDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Installed daily Windows task '$TaskName' at $RunAt local time."
