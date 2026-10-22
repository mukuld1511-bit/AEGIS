"""AEGIS Windows Startup and Desktop Shortcuts Setup Script.
Registers silent background launcher in Windows Startup and places 1-click Desktop shortcuts.
"""
import os
import sys
import subprocess

def create_shortcut(lnk_path, target, args="", work_dir="", desc=""):
    ps_cmd = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '{args}'; "
        f"$s.WorkingDirectory = '{work_dir}'; "
        f"$s.Description = '{desc}'; "
        f"$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    appdata = os.environ.get("APPDATA", "")
    startup_folder = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    desktop_folder = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    vbs_path = os.path.join(root_dir, "scripts", "start_aegis_silent.vbs")
    stop_bat_path = os.path.join(root_dir, "scripts", "stop_aegis.bat")

    print("=" * 65)
    print(" [AEGIS] Configuring Windows Silent Auto-Startup")
    print(f" Root:    {root_dir}")
    print(f" Startup: {startup_folder}")
    print(f" VBS:     {vbs_path}")
    print("=" * 65)

    # 1. Windows Startup Shortcut (Runs silently on boot)
    startup_lnk = os.path.join(startup_folder, "AEGIS_AutoStart.lnk")
    create_shortcut(startup_lnk, "wscript.exe", f'"{vbs_path}"', work_dir=root_dir, desc="AEGIS Multi-DGX AutoStart")
    print(f"[OK] Created Windows Startup Shortcut: {startup_lnk}")

    # 2. Desktop Shortcut: Start AEGIS (Silent launcher)
    desktop_start_lnk = os.path.join(desktop_folder, "Start AEGIS.lnk")
    create_shortcut(desktop_start_lnk, "wscript.exe", f'"{vbs_path}"', work_dir=root_dir, desc="Start AEGIS Cluster and HUD")
    print(f"[OK] Created Desktop Shortcut: {desktop_start_lnk}")

    # 3. Desktop Shortcut: Stop AEGIS (1-click terminator)
    desktop_stop_lnk = os.path.join(desktop_folder, "Stop AEGIS.lnk")
    create_shortcut(desktop_stop_lnk, stop_bat_path, work_dir=root_dir, desc="Stop all AEGIS background services")
    print(f"[OK] Created Desktop Shortcut: {desktop_stop_lnk}")

    # 4. Desktop Shortcut: Web Mission Control (http://localhost:9000/)
    web_url = os.path.join(desktop_folder, "AEGIS Mission Control.url")
    with open(web_url, "w", encoding="utf-8") as f:
        f.write("[InternetShortcut]\nURL=http://localhost:9000/\nIconIndex=0\n")
    print(f"[OK] Created Desktop Shortcut: {web_url}")

    print("\n" + "=" * 65)
    print("[SUCCESS] Windows Auto-Startup Configured 100%!")
    print("   1. When you turn on your PC / log in, AEGIS starts SILENTLY.")
    print("   2. Terminal is 100% closed (Zero black windows).")
    print("   3. Dynamic Island and Corner Neon Logo glide in with animation!")
    print("   4. Stop anytime using the 'Stop AEGIS' shortcut on your Desktop.")
    print("=" * 65)

if __name__ == "__main__":
    main()
