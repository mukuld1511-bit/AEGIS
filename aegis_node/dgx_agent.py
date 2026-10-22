#!/usr/bin/env python3
"""AEGIS Standalone DGX Spark Node Agent (dgx_agent.py).
Zero Dependencies / Self-Contained Single-File Agent:
- No whole repo needed. Just this 1 file on the DGX machine.
- Outbound polling every 6 seconds to Raspberry Pi Gateway (https://raspberrypi.tailc8c1f6.ts.net).
- Zero inbound open ports required (100% firewall / NAT traversal).
- Sends live telemetry (NVIDIA GPU utilization, VRAM, temp, active process, idle time).
- Runs local Ollama LLM (deepseek-coder-v2:16b).
- Auto-syncs generated code to i7 PC Vault (http://100.88.197.6:9080).
- Supports live supervisor commands: warn, lock, unlock, capture, pull_model, run_command, execute_task.
"""
import os
import sys
import time
import json
import socket
import argparse
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

def http_post_json(url: str, data: dict, timeout: float = 6.0) -> dict:
    """Sends JSON POST request using standard Python library (zero pip dependencies)."""
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "AEGIS-DGX-Agent/2.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

class DGXStandaloneAgent:
    def __init__(self, node_id: str = "dgx-node-1",
                 gateway_url: str = "https://raspberrypi.tailc8c1f6.ts.net",
                 fallback_url: str = "http://100.106.207.27:9000",
                 storage_url: str = "http://100.88.197.6:9080",
                 ollama_url: str = "http://127.0.0.1:11434",
                 default_model: str = "deepseek-coder-v2:16b",
                 poll_interval: float = 6.0):
        self.node_id = node_id
        self.gateway_url = gateway_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.storage_url = storage_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.default_model = default_model
        self.poll_interval = poll_interval

        self.current_task_id = None
        self.is_running = True
        self.is_locked = False
        os.makedirs("./workspace", exist_ok=True)

    def get_gpu_metrics(self) -> dict:
        """Reads NVIDIA GPU telemetry directly via nvidia-smi."""
        metrics = {
            "name": "NVIDIA GPU",
            "vram_used_mb": 0.0,
            "vram_total_mb": 131072.0,
            "utilization_pct": 0.0,
            "temperature_c": 35.0
        }
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                   "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2.0).decode().strip()
            if out:
                parts = [p.strip() for p in out.splitlines()[0].split(",")]
                if len(parts) >= 5:
                    metrics["name"] = parts[0]
                    metrics["vram_used_mb"] = float(parts[1])
                    metrics["vram_total_mb"] = float(parts[2])
                    metrics["utilization_pct"] = float(parts[3])
                    metrics["temperature_c"] = float(parts[4])
        except Exception:
            pass
        return metrics

    def get_active_window(self) -> str:
        """Gets active foreground process or window."""
        try:
            out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"],
                stderr=subprocess.DEVNULL, timeout=0.8
            ).decode(errors="ignore").strip()
            if out:
                return out
        except Exception:
            pass
        if self.current_task_id:
            return f"Ollama ({self.default_model}) - Task {self.current_task_id}"
        return "Terminal / Idle"

    def get_idle_seconds(self) -> float:
        """Gets idle time in seconds."""
        try:
            out = subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL, timeout=0.8).decode().strip()
            return round(int(out) / 1000.0, 1)
        except Exception:
            return 0.0

    def build_telemetry(self) -> dict:
        gpu = self.get_gpu_metrics()
        status = "locked" if self.is_locked else ("busy" if self.current_task_id else "online")

        # Get host CPU and RAM
        cpu_pct = 5.0
        ram_pct = 15.0
        try:
            with open("/proc/loadavg", "r") as f:
                cpu_pct = min(100.0, float(f.read().split()[0]) * 10.0)
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                total = int([l for l in lines if "MemTotal" in l][0].split()[1])
                avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
                ram_pct = round(((total - avail) / total) * 100, 1)
        except Exception:
            pass

        return {
            "node_id": self.node_id,
            "name": f"DGX Spark {self.node_id}",
            "ip": "127.0.0.1",
            "status": status,
            "current_task_id": self.current_task_id,
            "cpu_percent": cpu_pct,
            "ram_percent": ram_pct,
            "gpu": gpu,
            "active_model": self.default_model,
            "capabilities": ["code_generation", "code_review", "data_analysis"],
            "active_window": self.get_active_window(),
            "idle_time_seconds": self.get_idle_seconds(),
            "client_type": "dgx",
            "os_platform": "linux",
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        }

    def execute_ollama_query(self, prompt: str) -> str:
        """Queries local Ollama instance for code generation."""
        print(f"\n[{self.node_id}] Querying local model: {self.default_model}...")
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "stream": False
        }
        res = http_post_json(url, payload, timeout=120.0)
        return res.get("response", "")

    def upload_to_i7_vault(self, file_path: str, task_id: str) -> str:
        """Uploads generated script to i7-14700 PC Vault via curl."""
        if not os.path.exists(file_path):
            return "file_not_found"
        try:
            upload_url = f"{self.storage_url}/api/storage/{self.node_id}/upload/{task_id}"
            cmd = ["curl", "-s", "-F", f"file=@{file_path}", "-F", "stage=outputs", upload_url]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if "stored_in_vault" in res.stdout:
                return "synced_to_vault"
            return f"vault_response: {res.stdout[:100]}"
        except Exception as e:
            return f"error: {str(e)}"

    def execute_task(self, task: dict):
        if self.is_locked:
            print(f"[{self.node_id}] Task rejected: Node is LOCKED.")
            return

        task_id = task.get("task_id", f"tsk_{int(time.time())}")
        prompt = task.get("prompt", "")
        self.current_task_id = task_id

        print("\n" + "=" * 65)
        print(f"[{self.node_id}] REVERSE HEARTBEAT TASK RECEIVED: {task_id}")
        print(f"Prompt: {prompt}")
        print("=" * 65)

        # 1. Run inference on local GPU
        stdout_log = self.execute_ollama_query(prompt)
        print(f"\n--- Model Output Preview ---\n{stdout_log[:600]}...\n----------------------------")

        # 2. Extract code block and save to workspace
        generated_file = None
        if "```python" in stdout_log:
            code = stdout_log.split("```python")[1].split("```")[0].strip()
            generated_file = f"./workspace/{task_id}_output.py"
            with open(generated_file, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"[✓] Code saved locally: {generated_file}")
        elif "```" in stdout_log:
            code = stdout_log.split("```")[1].split("```")[0].strip()
            generated_file = f"./workspace/{task_id}_output.txt"
            with open(generated_file, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"[✓] Text saved locally: {generated_file}")

        # 3. Mirror file to i7 PC Vault
        vault_status = "none"
        if generated_file:
            vault_status = self.upload_to_i7_vault(generated_file, task_id)
            print(f"[✓] Vault Sync: {vault_status} -> {self.storage_url}")

        # 4. Report completion back to Raspberry Pi Gateway
        complete_payload = {
            "task_id": task_id,
            "node_id": self.node_id,
            "exit_code": 0,
            "stdout": stdout_log[:1500],
            "stderr": "",
            "generated_file": generated_file,
            "vault_status": vault_status,
            "drive_status": "not_requested"
        }

        for gw in [self.gateway_url, self.fallback_url]:
            res = http_post_json(f"{gw}/api/dgx/complete", complete_payload, timeout=6.0)
            if "status" in res:
                print(f"[✓] Task completion reported to {gw}")
                break

        self.current_task_id = None
        print(f"[{self.node_id}] Ready for next reverse heartbeat.\n")

    def handle_command(self, cmd: dict):
        cmd_id = cmd.get("command_id", f"cmd-{int(time.time())}")
        cmd_type = cmd.get("command_type")
        payload = cmd.get("payload", {})

        print(f"\n[{self.node_id}] INCOMING COMMAND: {cmd_type} ({cmd_id})")

        if cmd_type == "warn":
            msg = payload.get("message", "Operator alert")
            print(f"\n⚠️  [GATEWAY ALERT] {msg}\n")

        elif cmd_type == "lock":
            self.is_locked = True
            print(f"🔒 [LOCKED] Node placed in security lock mode.")

        elif cmd_type == "unlock":
            self.is_locked = False
            print(f"🔓 [UNLOCKED] Node resumed normal operations.")

        elif cmd_type == "pull_model":
            model_name = payload.get("model", self.default_model)
            print(f"[*] Pulling Ollama model: {model_name}...")
            subprocess.run(["ollama", "pull", model_name])

        elif cmd_type == "run_command":
            cmd_str = payload.get("command", "")
            print(f"[*] Running shell command: {cmd_str}")
            subprocess.run(cmd_str, shell=True)

        elif cmd_type == "execute_task":
            self.execute_task(payload)

    def start_polling(self):
        print("=" * 65)
        print(f" [AEGIS DGX STANDALONE AGENT] Active: {self.node_id}")
        print(f" Gateway URL:   {self.gateway_url} (Outbound HTTPS Polling)")
        print(f" Storage Vault: {self.storage_url}")
        print(f" Local Model:   {self.default_model} (Ollama: {self.ollama_url})")
        print(f" Polling Every: {self.poll_interval}s | Inbound Ports: ZERO")
        print("=" * 65)

        gateways = [self.gateway_url, self.fallback_url]

        while self.is_running:
            telem = self.build_telemetry()
            for gw in gateways:
                res = http_post_json(f"{gw}/api/client/heartbeat", telem, timeout=5.0)
                if res.get("status") == "acknowledged":
                    if res.get("has_command"):
                        self.handle_command(res["command"])
                    elif res.get("has_task"):
                        self.execute_task(res["task"])
                    break

            time.sleep(self.poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Standalone DGX Spark Node Agent")
    parser.add_argument("--id", default="dgx-node-1", help="Node ID (e.g., dgx-node-1)")
    parser.add_argument("--gateway", default="https://raspberrypi.tailc8c1f6.ts.net", help="Raspberry Pi Tailscale Gateway")
    parser.add_argument("--storage", default="http://100.88.197.6:9080", help="i7-14700 PC Vault URL")
    parser.add_argument("--model", default="deepseek-coder-v2:16b", help="Local Ollama model name")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds")
    args = parser.parse_args()

    agent = DGXStandaloneAgent(
        node_id=args.id,
        gateway_url=args.gateway,
        storage_url=args.storage,
        default_model=args.model,
        poll_interval=args.interval
    )
    try:
        agent.start_polling()
    except KeyboardInterrupt:
        print("\nAgent stopped.")
