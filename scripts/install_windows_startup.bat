@echo off
setlocal enabledelayedexpansion
title AEGIS Windows Auto-Startup Installer
echo ======================================================================
echo  🚀 [AEGIS] Configuring Windows Silent Auto-Startup
echo ======================================================================

set "PROJECT_DIR=%~dp0.."
pushd "!PROJECT_DIR!"
set "ROOT_DIR=!CD!"
popd

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_VBS=%ROOT_DIR%\scripts\start_aegis_silent.vbs"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"

echo [*] Project Root:     !ROOT_DIR!
echo [*] Silent Launcher:  !TARGET_VBS!
echo [*] Windows Startup:  !STARTUP_FOLDER!

:: 1. Create AutoStart shortcut in Startup folder
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!STARTUP_FOLDER!\AEGIS_AutoStart.lnk'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"!TARGET_VBS!\"'; $s.WorkingDirectory = '!ROOT_DIR!'; $s.Description = 'AEGIS Multi-DGX Cluster AutoStart'; $s.Save(); Write-Host '[✓] Auto-Startup shortcut created in Startup folder.'"

:: 2. Create Desktop Shortcut to Start Silently
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!DESKTOP_DIR!\Start AEGIS.lnk'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"!TARGET_VBS!\"'; $s.WorkingDirectory = '!ROOT_DIR!'; $s.Description = 'Start AEGIS Cluster & HUD Silently'; $s.Save(); Write-Host '[✓] Desktop shortcut created: Start AEGIS'"

:: 3. Create Desktop Shortcut to Stop Services
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!DESKTOP_DIR!\Stop AEGIS.lnk'); $s.TargetPath = '!ROOT_DIR!\scripts\stop_aegis.bat'; $s.WorkingDirectory = '!ROOT_DIR!'; $s.Description = 'Stop AEGIS Cluster & HUD'; $s.Save(); Write-Host '[✓] Desktop shortcut created: Stop AEGIS'"

:: 4. Create Desktop Shortcut for Web Mission Control (http://localhost:9000)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!DESKTOP_DIR!\AEGIS Mission Control.lnk'); $s.TargetPath = 'http://localhost:9000/'; $s.Description = 'AEGIS Web Dashboard'; $s.Save(); Write-Host '[✓] Desktop shortcut created: AEGIS Mission Control'"

echo.
echo ======================================================================
echo  ✅ [SUCCESS] Windows Auto-Startup Configured 100%!
echo     1. When you turn on your PC / log in, AEGIS starts SILENTLY.
echo     2. Terminal is 100% closed (Zero black windows).
echo     3. Dynamic Island & Corner Neon Logo glide in with animation!
echo     4. Stop anytime using the 'Stop AEGIS' shortcut on your Desktop.
echo ======================================================================
timeout /t 3 >nul 2>&1
