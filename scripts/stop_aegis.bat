@echo off
echo ======================================================================
echo  [AEGIS] Stopping background services and HUD...
echo ======================================================================

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":9000 :9080"') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM pythonw.exe >nul 2>&1

echo [OK] All AEGIS services and HUD stopped cleanly.
timeout /t 2 >nul 2>&1
