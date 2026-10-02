# Registers the daily PDL check.
#
# Run normally, or right-click and "Run as administrator" for the better version.
#
# Two modes:
#   S4U        - runs whether you are logged on or off. Needs elevation.
#   Interactive - runs while you are logged on (locked counts). No elevation
#                needed, so it also runs a missed check at logon.

$ErrorActionPreference = "Stop"

# --- elevate ourselves -------------------------------------------------------
# Registering the task so it runs whether you are logged on or off needs
# administrator. Rather than making you find "Run as administrator", this
# relaunches elevated and asks. It uses the script's own full path, so it does
# not matter which directory you run it from.
$self = $MyInvocation.MyCommand.Path
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "This needs administrator so the task runs whether you are logged on or off."
    Write-Host "Approve the prompt that is about to appear."
    Write-Host ""
    try {
        Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-Command", "& '$self'"
        )
    }
    catch {
        Write-Host "Elevation was declined or unavailable."
        Write-Host "Falling through to the no-elevation version - it only runs while"
        Write-Host "you are logged on."
        Write-Host ""
    }
    exit
}

$here = Split-Path -Parent $self
$task = "WA Apple Health PDL Watch"

$py = $null
foreach ($v in 312, 313, 311, 310) {
    $c = "$env:LocalAppData\Programs\Python\Python$v\python.exe"
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found. Install Python 3.9+ first." }
Write-Host "Using $py"

$arg = "`"$here\pdl_watch.py`" --quiet"

# Run through cmd.exe, and keep a log of what the scheduled run actually did.
# This is not decoration: launching python.exe *directly* as the task action
# fails with 0xFFFFFFFF, because the console app gets no console to attach to.
# Wrapping it is the fix.
$cmdline = "/c `"`"$py`" $arg > `"$here\sched.log`" 2>&1`""
$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmdline -WorkingDirectory $here

$daily   = New-ScheduledTaskTrigger -Daily -At 8:20am
$logon   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$logon.Delay = "PT3M"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -MultipleInstances IgnoreNew

# Try S4U first: the right answer, but it needs elevation to grant
# "log on as a batch job". If that is refused, fall back to something that
# still works without it rather than leaving you with no task at all.
$mode = "S4U (runs logged on or off)"
try {
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
    Register-ScheduledTask -TaskName $task `
        -Description "Watches the Washington Apple Health PDL for rescue glucagon coverage and PA changes." `
        -Action $action -Trigger @($daily) -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "Mode: S4U - runs whether you are logged on or not." -ForegroundColor Green
}
catch {
    $mode = "Interactive (runs when logged on, and at logon)"
    Register-ScheduledTask -TaskName $task `
        -Description "Watches the Washington Apple Health PDL for rescue glucagon coverage and PA changes." `
        -Action $action -Trigger @($daily, $logon) -Settings $settings -Force | Out-Null
    Write-Host "Mode: Interactive - elevation was refused, so this one only runs while you are" -ForegroundColor Yellow
    Write-Host "      logged on. It also runs 3 minutes after you log in, so a check missed" -ForegroundColor Yellow
    Write-Host "      while the machine was off still happens." -ForegroundColor Yellow
    Write-Host "      To upgrade: right-click this file and Run as administrator." -ForegroundColor Yellow
}

$info = Get-ScheduledTaskInfo -TaskName $task
Write-Host ""
Write-Host "Installed '$task'"
Write-Host "  Mode       : $mode"
Write-Host "  Next run   : $($info.NextRunTime)"
Write-Host "  History    : $here\history.jsonl"
Write-Host "  Run log    : $here\sched.log"
Write-Host ""
Write-Host "  Check it  : Get-ScheduledTaskInfo -TaskName '$task'"
Write-Host "  Run now   : Start-ScheduledTask -TaskName '$task'"
Write-Host "  Turn off  : Unregister-ScheduledTask -TaskName '$task' -Confirm:`$false"
Write-Host ""
Write-Host "Press Enter to close this window."
[void](Read-Host)
