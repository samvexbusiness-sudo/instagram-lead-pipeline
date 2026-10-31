# Registers a daily Windows scheduled task that runs footage-first sourcing and writes to Notion.
# Run ONCE, in PowerShell, from the repo folder, AFTER Sam has approved a dry run:
#   powershell -ExecutionPolicy Bypass -File scripts\schedule_daily_sourcing.ps1
# Remove it later with:  Unregister-ScheduledTask -TaskName "Samvex daily sourcing" -Confirm:$false
#
# Keys come from the repo's .env file (never committed): NOTION_TOKEN, ANTHROPIC_API_KEY,
# and optionally HUNTER_API_KEY. The job never emails or DMs anyone.

param(
  [string]$Time = "10:17",          # local time; off the hour on purpose
  [switch]$Hunter                    # add -Hunter to let it spend Hunter credits (cap in settings.toml)
)

$repo = (Resolve-Path "$PSScriptRoot\..").Path
$python = (Get-Command python).Source
$logDir = Join-Path $repo "data\sourcing\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$hunterFlag = if ($Hunter) { " --hunter" } else { "" }
$cmd = "cd /d `"$repo`" && `"$python`" run.py source --write --approve-spend$hunterFlag >> `"$logDir\sourcing.log`" 2>&1"

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd"
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "Samvex daily sourcing" -Action $action -Trigger $trigger -Settings $settings `
  -Description "Footage-first prospect sourcing into Notion (no outreach)" -Force | Out-Null

Write-Host "Scheduled 'Samvex daily sourcing' every day at $Time. Log: $logDir\sourcing.log"
Write-Host "Run it now to test:  Start-ScheduledTask -TaskName 'Samvex daily sourcing'"
