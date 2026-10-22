@echo off
setlocal enabledelayedexpansion
title Remove AEGIS from Windows Startup
echo ======================================================================
echo  [AEGIS] Removing AEGIS from Windows Startup...
echo ======================================================================

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

if exist "%STARTUP_FOLDER%\AEGIS_AutoStart.lnk" (
    del /f /q "%STARTUP_FOLDER%\AEGIS_AutoStart.lnk"
    echo [✓] Removed AEGIS_AutoStart.lnk from Startup folder.
) else (
    echo [*] AEGIS_AutoStart.lnk was not found in Startup folder.
)

echo ======================================================================
echo  [✓] Complete.
echo ======================================================================
timeout /t 2 >nul
