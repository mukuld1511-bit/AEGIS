"""AEGIS Reverse-Heartbeat DGX Node Agent.
Based on Reverse-Heartbeat Architecture (Tailscale Funnel):
- Zero inbound open ports on DGX nodes.
- Bypasses all strict campus/lab firewalls and NAT.
- Outbound HTTPS heartbeats to Raspberry Pi Funnel (https://raspberrypi.tailc8c1f6.ts.net) every 6 seconds.
- Telemetry includes active window, idle time, GPU VRAM, and screenshot buffer.
- Receives pending commands (warn, lock, shutdown, capture, execute_task, pull_model, run_command) inside heartbeat HTTP response.
- Runs local Ollama LLM, updates physical screen HUD, syncs artifacts to i7 PC vault, and reports back.
"""
import asyncio
import os
import sys
import time
import io
import base64
import json
import argparse
import subprocess
import httpx
from datetime import datetime, timezone

# Add workspace to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aegis_core.models import NodeTelemetry, GPUInfo, CommandResult
from aegis_node.gpu_telemetry import GPUTelemetryReporter
from aegis_node.terminal_session import TerminalSession
from aegis_node.llm_runner import LLMRunner
from aegis_node.overlay.overlay_hud import OverlayHUD

class DGXReverseAgent:
    def __init__(self, node_id: str = "dgx-node-1", 
                 gateway_url: str = "https://raspberrypi.tailc8c1f6.ts.net",
                 fallback_coordinator_url: str = "http://100.106.207.27:9000",
                 storage_vault_url: str = "http://100.88.197.6:9080",
                 poll_interval: float = 6.0,
                 show_hud: bool = True):
        self.node_id = node_id
        self.gateway_url = gateway_url.rstrip("/")
        self.fallback_url = fallback_coordinator_url.rstrip("/")
        self.storage_vault_url = storage_vault_url.rstrip("/")
        self.poll_interval = poll_interval
        self.show_hud = show_hud

        self.telemetry = GPUTelemetryReporter()
        self.llm = LLMRunner()
        self.current_task_id = None
        self.is_running = True
        self.is_locked = False
        self.hud = None

        if self.show_hud:
            try:
                self.hud = OverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                self.hud.start_hud_thread()
            except Exception as e:
                print(f"[{self.node_id}] Note: Overlay HUD disabled ({e})")

    def get_active_window(self) -> str:
        """Detects active foreground window title or active compute process."""
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    return buf.value.strip() or "Desktop"
            except Exception:
                pass
        else:
            # Linux X11 or Wayland
            try:
                out = subprocess.check_output(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    stderr=subprocess.DEVNULL, timeout=0.8
                ).decode("utf-8", errors="ignore").strip()
                if out:
                    return out
            except Exception:
                pass
        
        # Fallback to active model or status
        if self.current_task_id:
            return f"Ollama: {self.llm.default_model} (Task {self.current_task_id})"
        return "Terminal / System Idle"

    def get_idle_seconds(self) -> float:
        """Calculates user idle time in seconds."""
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
        else:
            try:
                out = subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL, timeout=0.8).decode().strip()
                return round(int(out) / 1000.0, 1)
            except Exception:
                pass
        return 0.0

    def capture_screenshot_b64(self, thumbnail: bool = True) -> str:
        """Grabs screen snapshot, resizes to compact thumbnail, and encodes as base64."""
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

    def get_heartbeat_payload(self) -> dict:
        gpu_data = self.telemetry.get_metrics()
        host_data = self.telemetry.get_host_metrics()
        
        status = "locked" if self.is_locked else ("busy" if self.current_task_id else "online")

        telemetry = NodeTelemetry(
            node_id=self.node_id,
            name=f"DGX Spark {self.node_id}",
            ip="127.0.0.1",
            status=status,
            current_task_id=self.current_task_id,
            cpu_percent=host_data["cpu_percent"],
            ram_percent=host_data["ram_percent"],
            gpu=GPUInfo(**gpu_data),
            active_model=self.llm.default_model,
            capabilities=["code_generation", "code_review", "data_analysis"],
            active_window=self.get_active_window(),
            idle_time_seconds=self.get_idle_seconds(),
            screenshot_b64=self.capture_screenshot_b64(thumbnail=True),
            client_type="dgx",
            os_platform="linux" if sys.platform != "win32" else "windows"
        )
        return telemetry.model_dump(mode="json")

    async def report_command_result(self, cmd_id: str, status: str, output: str = "", error: str = "", shot: str = ""):
        """Sends command execution result back to the central gateway."""
        payload = CommandResult(
            command_id=cmd_id,
            node_id=self.node_id,
            status=status,
            output=output,
            error=error,
            screenshot_b64=shot
        )
        gateways = [self.gateway_url, self.fallback_url]
        for gw in gateways:
            try:
                async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
                    await client.post(f"{gw}/api/client/command_result", json=payload.model_dump(mode="json"))
                    break
            except Exception:
                pass

    async def handle_supervisor_command(self, cmd: dict):
        """Executes administrative or control commands received from the hub."""
        cmd_id = cmd.get("command_id", f"cmd-{int(time.time())}")
        cmd_type = cmd.get("command_type", "")
        payload = cmd.get("payload", {})

        print(f"\n[{self.node_id}] RECEIVED COMMAND: {cmd_type} (ID: {cmd_id})")

        if cmd_type == "warn":
            msg = payload.get("message", "Lab Operator Notice")
            print(f"⚠️ [ALERT] {msg}")
            if self.hud:
                self.hud.show_warning(msg)
            await self.report_command_result(cmd_id, "completed", output=f"Warning displayed: {msg}")

        elif cmd_type == "lock":
            reason = payload.get("reason", "Locked by operator")
            self.is_locked = True
            print(f"🔒 [LOCKED] {reason}")
            if self.hud:
                self.hud.set_locked(True, reason)
            await self.report_command_result(cmd_id, "completed", output=f"Node locked: {reason}")

        elif cmd_type == "unlock":
            self.is_locked = False
            print(f"🔓 [UNLOCKED]")
            if self.hud:
                self.hud.set_locked(False)
            await self.report_command_result(cmd_id, "completed", output="Node unlocked")

        elif cmd_type == "capture":
            shot = self.capture_screenshot_b64(thumbnail=False)
            await self.report_command_result(cmd_id, "completed", output="Screenshot captured", shot=shot)

        elif cmd_type == "pull_model":
            model_name = payload.get("model", self.llm.default_model)
            if self.hud:
                self.hud.append_log(f"\n[PULL] Executing: ollama pull {model_name}...\n")
            sess = TerminalSession(session_id=f"pull_{int(time.time())}")
            out_log = ""
            async for _, chk in sess.execute_command_stream(f"ollama pull {model_name}"):
                out_log += chk
                if self.hud:
                    self.hud.append_log(chk)
            await self.report_command_result(cmd_id, "completed" if sess.exit_code == 0 else "failed", output=out_log[:500])

        elif cmd_type == "run_command":
            cmd_str = payload.get("command", "")
            if self.hud:
                self.hud.append_log(f"\n[EXEC] {cmd_str}\n")
            sess = TerminalSession(session_id=f"cmd_{int(time.time())}")
            out_log = ""
            async for _, chk in sess.execute_command_stream(cmd_str):
                out_log += chk
                if self.hud:
                    self.hud.append_log(chk)
            await self.report_command_result(cmd_id, "completed" if sess.exit_code == 0 else "failed", output=out_log[:500])

        elif cmd_type == "execute_task":
            await self.execute_task_payload(payload)

        elif cmd_type == "shutdown":
            reason = payload.get("reason", "Shutdown command")
            if self.hud:
                self.hud.append_log(f"\n[SHUTDOWN] System shutting down: {reason}\n")
            await self.report_command_result(cmd_id, "completed", output="Shutdown initiated")
            print(f"[{self.node_id}] Shutdown requested: {reason}")

    async def execute_task_payload(self, task: dict):
        if self.is_locked:
            print(f"[{self.node_id}] Cannot execute task: Node is currently LOCKED.")
            return

        task_id = task.get("task_id", f"tsk_{int(time.time())}")
        prompt = task.get("prompt", "")
        cmd = task.get("command")
        self.current_task_id = task_id

        print(f"\n=======================================================")
        print(f"[{self.node_id}] REVERSE HEARTBEAT RECEIVED TASK: {task_id}")
        print(f"Prompt: {prompt}")
        print(f"=======================================================")

        if self.hud:
            self.hud.update_status("BUSY", task_title=prompt)
            self.hud.append_log(f"\n>>> [TASK {task_id}] Received from Raspberry Pi Gateway:\nPrompt: {prompt}\n")

        stdout_log = ""
        stderr_log = ""
        generated_file = None
        exit_code = 0

        # If a shell command was provided, execute in terminal
        if cmd:
            session = TerminalSession(session_id=task_id)
            async for sname, chunk in session.execute_command_stream(cmd):
                if sname == "stdout":
                    stdout_log += chunk
                else:
                    stderr_log += chunk
                if self.hud:
                    self.hud.append_log(chunk)
            exit_code = session.exit_code or 0
        else:
            # Query local Ollama model
            if self.hud:
                self.hud.append_log(f"[{self.node_id}] Querying local GPU model ({self.llm.default_model})...\n")
            
            async for token in self.llm.generate_response(prompt):
                stdout_log += token
                if self.hud:
                    self.hud.append_log(token)

            # Check if code block generated
            if "```python" in stdout_log:
                os.makedirs("./workspace", exist_ok=True)
                code = stdout_log.split("```python")[1].split("```")[0].strip()
                generated_file = f"./workspace/{task_id}_output.py"
                with open(generated_file, "w", encoding="utf-8") as f:
                    f.write(code)
                if self.hud:
                    self.hud.append_log(f"\n[SAVED FILE] {generated_file}\n")

        # Upload file to i7-14700 PC Vault
        vault_status = "none"
        if generated_file and os.path.exists(generated_file):
            try:
                fname = os.path.basename(generated_file)
                upload_url = f"{self.storage_vault_url}/api/storage/{self.node_id}/upload/{task_id}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    with open(generated_file, "rb") as uf:
                        res = await client.post(upload_url, files={"file": (fname, uf, "text/plain")}, data={"stage": "outputs"})
                        if res.status_code == 200:
                            vault_status = "synced_to_vault"
                            if self.hud:
                                self.hud.append_log(f"[VAULT] Uploaded {fname} to local i7 PC vault.\n")
            except Exception as e:
                vault_status = f"error: {str(e)}"

        # Upload to Google Drive if dictated
        drive_status = "not_requested"
        dictated_drive_cmd = task.get("dictated_upload_cmd")
        if dictated_drive_cmd:
            upload_sess = TerminalSession(session_id=f"{task_id}_drive")
            async for _, chk in upload_sess.execute_command_stream(dictated_drive_cmd):
                if self.hud:
                    self.hud.append_log(chk)
            drive_status = "drive_synced" if upload_sess.exit_code == 0 else "drive_failed"

        # Report completion back to Raspberry Pi Gateway
        complete_payload = {
            "task_id": task_id,
            "node_id": self.node_id,
            "exit_code": exit_code,
            "stdout": stdout_log[:1500],
            "stderr": stderr_log,
            "generated_file": generated_file,
            "vault_status": vault_status,
            "drive_status": drive_status
        }

        target_gateways = [self.gateway_url, self.fallback_url]
        for gw in target_gateways:
            try:
                async with httpx.AsyncClient(verify=False, timeout=6.0) as client:
                    await client.post(f"{gw}/api/dgx/complete", json=complete_payload)
                    break
            except Exception:
                pass

        self.current_task_id = None
        if self.hud:
            status_text = "LOCKED" if self.is_locked else "ONLINE"
            self.hud.update_status(status_text, task_title="Idle")
            self.hud.append_log(f"\n[Task {task_id} Completed - Ready for next heartbeat]\n")

    async def start_polling(self):
        print("==================================================================")
        print(f" [AEGIS DGX CLIENT] Reverse-Heartbeat Agent Active: {self.node_id}")
        print(f" Gateway URL:   {self.gateway_url} (HTTPS Outbound)")
        print(f" Storage Vault: {self.storage_vault_url}")
        print(f" Polling Every: {self.poll_interval}s | Inbound Open Ports: ZERO")
        print("==================================================================")

        gateways = [self.gateway_url, self.fallback_url]

        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            while self.is_running:
                # Update HUD telemetry
                gpu_data = self.telemetry.get_metrics()
                if self.hud:
                    telem_str = f"GPU: {gpu_data['utilization_pct']}% | VRAM: {gpu_data['vram_used_mb']/1024:.1f}/{gpu_data['vram_total_mb']/1024:.0f} GB | {gpu_data['temperature_c']}°C"
                    self.hud.update_telemetry(telem_str)

                # Send outbound heartbeat to Gateway
                heartbeat_data = self.get_heartbeat_payload()
                for gw in gateways:
                    try:
                        res = await client.post(f"{gw}/api/client/heartbeat", json=heartbeat_data)
                        if res.status_code == 200:
                            data = res.json()
                            # Check for supervisor command (warn, lock, shutdown, capture, pull_model)
                            if data.get("has_command"):
                                cmd = data["command"]
                                await self.handle_supervisor_command(cmd)
                            # Check for legacy compute task
                            elif data.get("has_task"):
                                task = data["task"]
                                await self.execute_task_payload(task)
                            break
                    except Exception:
                        pass

                await asyncio.sleep(self.poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Reverse-Heartbeat DGX Agent")
    parser.add_argument("--id", default="dgx-node-1", help="Node ID (e.g., dgx-node-1)")
    parser.add_argument("--gateway", default="https://raspberrypi.tailc8c1f6.ts.net", help="Raspberry Pi Tailscale Funnel Gateway")
    parser.add_argument("--fallback", default="http://100.106.207.27:9000", help="Direct Tailscale mesh fallback")
    parser.add_argument("--storage", default="http://100.88.197.6:9080", help="i7-14700 PC Vault URL")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds (default 6s)")
    parser.add_argument("--hud", action="store_true", help="Display desktop overlay HUD")
    args = parser.parse_args()

    agent = DGXReverseAgent(
        node_id=args.id,
        gateway_url=args.gateway,
        fallback_coordinator_url=args.fallback,
        storage_vault_url=args.storage,
        poll_interval=args.interval,
        show_hud=args.hud
    )

    try:
        asyncio.run(agent.start_polling())
    except KeyboardInterrupt:
        print("\nAgent stopped.")
