# ==============================================================================
# AEGIS Windows Auto-Startup & Desktop Shortcuts Installer (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$startupFolder = [System.Environment]::GetFolderPath("Startup")
$desktopFolder = [System.Environment]::GetFolderPath("Desktop")
$vbsPath = Join-Path $rootDir "scripts\start_aegis_silent.vbs"
$stopBatPath = Join-Path $rootDir "scripts\stop_aegis.bat"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🚀 [AEGIS] Configuring Windows Silent Auto-Startup & Desktop Shortcuts" -ForegroundColor Green
Write-Host "   Root Directory:    $rootDir"
Write-Host "   Startup Folder:    $startupFolder"
Write-Host "   Silent Launcher:   $vbsPath"
Write-Host "======================================================================" -ForegroundColor Cyan

$wsh = New-Object -ComObject WScript.Shell

# 1. Shortcut in Windows Startup folder (auto-boots with Windows)
$startupShortcutPath = Join-Path $startupFolder "AEGIS_AutoStart.lnk"
$sc = $wsh.CreateShortcut($startupShortcutPath)
$sc.TargetPath = "wscript.exe"
$sc.Arguments = "`"$vbsPath`""
$sc.WorkingDirectory = $rootDir
$sc.Description = "AEGIS Multi-DGX Cluster AutoStart (Silent)"
$sc.Save()
Write-Host "[✓] Windows Startup Shortcut: $startupShortcutPath" -ForegroundColor Green

# 2. Desktop Shortcut: "Start AEGIS" (Silent launcher)
$startDesktopPath = Join-Path $desktopFolder "Start AEGIS.lnk"
$sc2 = $wsh.CreateShortcut($startDesktopPath)
$sc2.TargetPath = "wscript.exe"
$sc2.Arguments = "`"$vbsPath`""
$sc2.WorkingDirectory = $rootDir
$sc2.Description = "Start AEGIS Background Services & Dynamic Island HUD"
$sc2.Save()
Write-Host "[✓] Desktop Shortcut: Start AEGIS" -ForegroundColor Green

# 3. Desktop Shortcut: "Stop AEGIS" (1-click terminator)
$stopDesktopPath = Join-Path $desktopFolder "Stop AEGIS.lnk"
$sc3 = $wsh.CreateShortcut($stopDesktopPath)
$sc3.TargetPath = $stopBatPath
$sc3.WorkingDirectory = $rootDir
$sc3.Description = "Stop all AEGIS background services"
$sc3.Save()
Write-Host "[✓] Desktop Shortcut: Stop AEGIS" -ForegroundColor Green

# 4. Desktop Shortcut: "AEGIS Mission Control" (Web browser link)
$webDesktopPath = Join-Path $desktopFolder "AEGIS Mission Control.url"
@"
[InternetShortcut]
URL=http://localhost:9000/
IconIndex=0
"@ | Set-Content -Path $webDesktopPath -Encoding utf8
Write-Host "[✓] Desktop Shortcut: AEGIS Mission Control (http://localhost:9000/)" -ForegroundColor Green

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "✅ [SUCCESS] Windows Auto-Startup Configured 100%!" -ForegroundColor Green
Write-Host "   1. On PC Boot: AEGIS starts silently in background."
Write-Host "   2. Zero black terminal windows open."
Write-Host "   3. Dynamic Island & Corner Neon Logo glide in with animation!"
Write-Host "   4. To stop anytime: Click 'Stop AEGIS' on your Desktop."
Write-Host "======================================================================" -ForegroundColor Cyan
