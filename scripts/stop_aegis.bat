@echo off
title Stop AEGIS Background Services
echo ======================================================================
echo  [AEGIS] Stopping all background services and HUD...
echo ======================================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_aegis*' -or $_.CommandLine -like '*aegis_hud_launcher*' -or $_.CommandLine -like '*dgx_agent*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[✓] Stopped process ' + $_.ProcessId + ': ' + $_.Name) }"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = @(9000, 9080); foreach ($p in $ports) { $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue; foreach ($c in $conns) { if ($c.OwningProcess) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host ('[✓] Released port ' + $p + ' (PID: ' + $c.OwningProcess + ')') } } }"

echo.
echo ======================================================================
echo  [✓] All AEGIS services & HUD stopped cleanly.
echo ======================================================================
timeout /t 2 >nul
