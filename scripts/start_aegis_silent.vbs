' ==============================================================================
' AEGIS Silent Windows Startup Launcher
' Launches AEGIS Coordinator (9000), Storage Vault (9080), and Desktop HUD
' completely in the background with ZERO black console windows.
' ==============================================================================
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get project root directory
scriptPath = WScript.ScriptFullName
scriptsDir = fso.GetParentFolderName(scriptPath)
rootDir = fso.GetParentFolderName(scriptsDir)

' Change working directory to rootDir
WshShell.CurrentDirectory = rootDir

' 1. Launch AEGIS Core Coordinator & i7 Storage Vault silently (WindowStyle 0 = Hidden)
cmdServer = "pythonw run_aegis.py --all"
WshShell.Run cmdServer, 0, False

' Wait 2 seconds for server startup
WScript.Sleep 2000

' 2. Launch Parakeet AI Neon Green Dynamic Island & Corner HUD (WindowStyle 0 = Hidden console)
cmdHUD = "pythonw scripts\aegis_hud_launcher.pyw"
WshShell.Run cmdHUD, 0, False
