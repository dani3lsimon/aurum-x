Set-ExecutionPolicy Bypass -Scope Process -Force
$ProgressPreference = "SilentlyContinue"
$DIR   = "C:\kronos"
$PORT  = 8765
$TOKEN = "kronos-aurum-$(Get-Random -Maximum 999999)"
$REPO  = "https://raw.githubusercontent.com/dani3lsimon/aurum-x/main/kronos"

Write-Host "=== Kronos VPS Setup ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $DIR | Out-Null

Write-Host "[1] Downloading server files from GitHub..." -ForegroundColor Yellow
Invoke-WebRequest "$REPO/kronos_server.py"  -OutFile "$DIR\kronos_server.py"
Invoke-WebRequest "$REPO/requirements.txt" -OutFile "$DIR\requirements.txt"
Write-Host "     Done." -ForegroundColor Green

Write-Host "[2] Checking Python..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "     Installing Python 3.11..." -ForegroundColor Gray
    $pyExe = "$env:TEMP\py311.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $pyExe
    Start-Process $pyExe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=0" -Wait
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + $env:PATH
    Write-Host "     Python 3.11 installed." -ForegroundColor Green
} else {
    Write-Host "     $(python --version)" -ForegroundColor Green
}

Write-Host "[3] Checking Git..." -ForegroundColor Yellow
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "     Installing Git..." -ForegroundColor Gray
    $gitExe = "$env:TEMP\git.exe"
    Invoke-WebRequest "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe" -OutFile $gitExe
    Start-Process $gitExe -ArgumentList "/VERYSILENT /NORESTART" -Wait
    $env:PATH += ";C:\Program Files\Git\cmd"
    Write-Host "     Git installed." -ForegroundColor Green
} else {
    Write-Host "     $(git --version)" -ForegroundColor Green
}

Write-Host "[4] Writing startup files..." -ForegroundColor Yellow
"KRONOS_AUTH_TOKEN=$TOKEN" | Set-Content "$DIR\.env" -Encoding ascii
("@echo off","set KRONOS_AUTH_TOKEN=$TOKEN","cd /d C:\kronos","C:\kronos\venv\Scripts\uvicorn.exe kronos_server:app --host 0.0.0.0 --port $PORT --workers 1") | Set-Content "$DIR\start_kronos.bat" -Encoding ascii
Write-Host "     Done." -ForegroundColor Green

Write-Host "[5] Creating venv and installing packages (~5-10 min)..." -ForegroundColor Yellow
python -m venv "$DIR\venv"
& "$DIR\venv\Scripts\pip.exe" install --upgrade pip -q
& "$DIR\venv\Scripts\pip.exe" install -r "$DIR\requirements.txt"
Write-Host "     Packages installed." -ForegroundColor Green

Write-Host "[6] Opening firewall port $PORT..." -ForegroundColor Yellow
netsh advfirewall firewall delete rule name="Kronos" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Kronos" protocol=TCP dir=in localport=$PORT action=allow | Out-Null
Write-Host "     Firewall rule added." -ForegroundColor Green

Write-Host "[7] Registering auto-start task..." -ForegroundColor Yellow
$a = New-ScheduledTaskAction -Execute "$DIR\start_kronos.bat"
$t = New-ScheduledTaskTrigger -AtLogOn
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "KronosForecastService" -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null
Write-Host "     Task registered." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " SETUP COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host " Add to Railway environment variables:" -ForegroundColor Yellow
Write-Host " KRONOS_SERVICE_URL = http://5.181.6.98:$PORT" -ForegroundColor Cyan
Write-Host " KRONOS_AUTH_TOKEN  = $TOKEN" -ForegroundColor Cyan
Write-Host ""
Write-Host " Starting Kronos now..." -ForegroundColor Yellow
Start-Process "$DIR\start_kronos.bat"
Write-Host " First startup downloads the model (~500MB) — takes 2-3 min." -ForegroundColor Gray
