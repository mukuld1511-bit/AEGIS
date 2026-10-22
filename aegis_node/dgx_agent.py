#!/usr/bin/env python3
"""AEGIS Standalone DGX Spark Node Agent with Floating Screen Overlay HUD (dgx_agent.py).
Zero External Pip Dependencies (Uses Python standard library + Tkinter).
- Floating Desktop Screen HUD: Borderless, semi-transparent HUD on top-right of DGX monitor (:0).
- Outbound polling every 6 seconds to Raspberry Pi Gateway (https://raspberrypi.tailc8c1f6.ts.net).
- Zero inbound open ports required (100% firewall / NAT traversal).
- Live NVIDIA GPU telemetry (utilization, VRAM used/total, temp).
- Runs local Ollama LLM (deepseek-coder-v2:16b).
- Auto-syncs generated code to i7 PC Vault (http://100.88.197.6:9080).
- Live supervisor commands: warn, lock, unlock, capture, pull_model, run_command, execute_task.
"""
import os
import re
import sys
import math
import time
import json
import queue
import socket
import argparse
import threading
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# Optional Tkinter for Desktop HUD
try:
    import tkinter as tk
    HAS_TK = True
except ImportError:
    HAS_TK = False

class OverlayHUD:
    """Floating minimalist head-up-display: Circular transparent logo orb that animates into full studio console."""
    def __init__(self, node_id: str = "dgx-node-1", node_name: str = "DGX Spark 01"):
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()
        self.root = None
        self.is_expanded = False
        self.is_animating = False
        self.current_status = "ONLINE"
        self.pulse_phase = False

        self.circle_size = 56
        self.full_width = 460
        self.full_height = 310
        self.pos_y = 24
        self.screen_width = 1920
        self._drag_x = 0
        self._drag_y = 0

    def start_hud_thread(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        try:
            self.root = tk.Tk()
            self.root.title(f"AEGIS - {self.node_id}")
            self.root.overrideredirect(True) # Borderless floating window
            self.root.attributes("-topmost", True) # Always on top

            # Semi-transparent window background
            try:
                self.root.attributes("-alpha", 0.94)
            except Exception:
                pass

            self.screen_width = self.root.winfo_screenwidth()
            pos_x_mini = self.screen_width - self.circle_size - 24
            self.root.geometry(f"{self.circle_size}x{self.circle_size}+{pos_x_mini}+{self.pos_y}")

            # Minimalist Modern Studio Palette (Obsidian & Charcoal)
            bg_dark = "#18181b"       # Neutral obsidian matte
            card_bg = "#27272a"       # Clean dark slate
            border_subtle = "#3f3f46" # 1px hairline border
            text_primary = "#f4f4f5"  # Crisp off-white
            text_muted = "#a1a1aa"    # Neutral slate secondary
            code_bg = "#09090b"       # Matte editor dark
            code_fg = "#e4e4e7"       # Editor clean gray-white

            self.root.configure(bg=bg_dark)

            # Outer border container
            self.main_container = tk.Frame(self.root, bg=bg_dark, highlightbackground=border_subtle, highlightthickness=1)
            self.main_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

            # ========================================================
            # 1. CIRCULAR TRANSPARENT LOGO ORB (Idle State)
            # ========================================================
            self.circle_canvas = tk.Canvas(
                self.main_container,
                width=self.circle_size,
                height=self.circle_size,
                bg=bg_dark,
                highlightthickness=0,
                cursor="hand2"
            )
            self.circle_canvas.pack(fill=tk.BOTH, expand=True)

            # Minimalist circular emblem
            self.orb_outer = self.circle_canvas.create_oval(3, 3, 51, 51, fill="#24242b", outline="#3f3f46", width=1.5)
            self.orb_ring = self.circle_canvas.create_oval(7, 7, 47, 47, outline="#10b981", width=1.2)
            self.orb_text = self.circle_canvas.create_text(27, 26, text="⬡", fill="#ffffff", font=("Helvetica", 15, "bold"))
            self.orb_pip = self.circle_canvas.create_oval(36, 36, 46, 46, fill="#10b981", outline="#18181b", width=1.5)

            # Click circular logo to expand
            self.circle_canvas.bind("<Button-1>", lambda e: self.start_animation(True))

            # ========================================================
            # 2. FULL CONSOLE HUD (Expanded State)
            # ========================================================
            self.full_frame = tk.Frame(self.main_container, bg=bg_dark)

            # Header
            hdr = tk.Frame(self.full_frame, bg=card_bg, height=34)
            hdr.pack(fill=tk.X, padx=0, pady=0)

            self.status_dot = tk.Label(hdr, text="●", fg="#10b981", bg=card_bg, font=("Helvetica", 10))
            self.status_dot.pack(side=tk.LEFT, padx=(10, 4))

            title_lbl = tk.Label(hdr, text=f"AEGIS Studio  •  {self.node_name}", fg=text_primary, bg=card_bg, font=("Helvetica", 9, "bold"))
            title_lbl.pack(side=tk.LEFT)

            # Minimal collapse button [ — ]
            collapse_btn = tk.Label(hdr, text="—", fg=text_muted, bg=card_bg, cursor="hand2", font=("Helvetica", 10, "bold"))
            collapse_btn.pack(side=tk.RIGHT, padx=(4, 10))
            collapse_btn.bind("<Button-1>", lambda e: self.start_animation(False))

            self.status_lbl = tk.Label(hdr, text="ONLINE", fg="#10b981", bg=card_bg, font=("Helvetica", 8, "bold"))
            self.status_lbl.pack(side=tk.RIGHT, padx=4)

            # Body Container
            body = tk.Frame(self.full_frame, bg=bg_dark)
            body.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

            # Telemetry Bar
            self.telem_lbl = tk.Label(
                body,
                text="GPU 0%  •  VRAM 0.0/128 GB  •  35°C",
                fg=text_muted,
                bg=bg_dark,
                font=("Consolas", 8)
            )
            self.telem_lbl.pack(anchor="w", padx=2, pady=(0, 2))

            # Task info
            self.task_lbl = tk.Label(
                body,
                text="Idle • Ready for tasks",
                fg="#71717a",
                bg=bg_dark,
                font=("Helvetica", 8),
                wraplength=440,
                justify="left"
            )
            self.task_lbl.pack(anchor="w", padx=2, pady=(0, 6))

            # Terminal log display area
            self.log_text = tk.Text(
                body,
                bg=code_bg,
                fg=code_fg,
                insertbackground="#f4f4f5",
                font=("Consolas", 8),
                height=11,
                wrap="char",
                borderwidth=0,
                highlightthickness=0
            )
            self.log_text.pack(fill=tk.BOTH, expand=True)
            self.log_text.insert(tk.END, "AEGIS Autonomous Agent Online.\nConnected via Reverse-Heartbeat to Gateway.\n")

            # Enable window dragging on both circular orb and header
            self._bind_drag(self.circle_canvas)
            self._bind_drag(hdr)

            # Start breathing pulse loop and queue processor
            self.root.after(100, self._process_queue)
            self.root.after(1200, self._pulse_loop)
            self.root.mainloop()
        except Exception as e:
            print(f"[OverlayHUD] GUI error: {e}")

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        widget.bind("<B1-Motion>", self._on_drag_motion, add="+")

    def _on_drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event):
        if self.root and not self.is_animating:
            x = self.root.winfo_x() - self._drag_x + event.x
            y = self.root.winfo_y() - self._drag_y + event.y
            self.root.geometry(f"+{x}+{y}")

    def _pulse_loop(self):
        """Gentle breathing animation for the circular logo orb when idle."""
        if not self.root:
            return
        if not self.is_expanded and not self.is_animating:
            self.pulse_phase = not self.pulse_phase
            base_col = "#10b981" if self.current_status in ["ONLINE", "READY"] else "#f59e0b"
            dim_col = "#047857" if self.current_status in ["ONLINE", "READY"] else "#b45309"
            cur = base_col if self.pulse_phase else dim_col
            self.circle_canvas.itemconfig(self.orb_ring, outline=cur)
            self.circle_canvas.itemconfig(self.orb_pip, fill=cur)
        self.root.after(1200, self._pulse_loop)

    def toggle_expand(self):
        self.start_animation(not self.is_expanded)

    def set_expanded(self, expand: bool):
        self.log_queue.put(("expand", expand))

    def start_animation(self, target_expanded: bool):
        """Smooth animated cubic-ease transition between circular logo and full HUD."""
        if self.is_animating or self.is_expanded == target_expanded:
            return

        self.is_animating = True
        self.target_expanded = target_expanded

        if target_expanded:
            self.circle_canvas.pack_forget()
            self.full_frame.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.circle_size, self.circle_size
            end_w, end_h = self.full_width, self.full_height
        else:
            self.full_frame.pack_forget()
            self.circle_canvas.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.full_width, self.full_height
            end_w, end_h = self.circle_size, self.circle_size

        self._step_animation(1, 14, start_w, end_w, start_h, end_h)

    def _step_animation(self, step, total_steps, start_w, end_w, start_h, end_h):
        if not self.root:
            self.is_animating = False
            return

        t = step / float(total_steps)
        # Cubic ease-out formula
        ease = 1.0 - math.pow(1.0 - t, 3)

        w = int(start_w + (end_w - start_w) * ease)
        h = int(start_h + (end_h - start_h) * ease)
        current_x = self.root.winfo_x()
        current_y = self.root.winfo_y()
        pos_x = min(current_x, self.screen_width - w - 16)

        self.root.geometry(f"{w}x{h}+{pos_x}+{current_y}")

        if step < total_steps:
            self.root.after(14, self._step_animation, step + 1, total_steps, start_w, end_w, start_h, end_h)
        else:
            self.is_expanded = self.target_expanded
            self.is_animating = False
            border = "#f59e0b" if self.current_status == "BUSY" else "#3f3f46"
            self.main_container.configure(highlightbackground=border)

    def _auto_collapse_if_idle(self):
        if self.current_status in ["ONLINE", "READY"] and self.is_expanded:
            self.start_animation(False)

    def append_log(self, text: str):
        self.log_queue.put(("log", text))

    def update_status(self, status: str, task_title: str = ""):
        self.log_queue.put(("status", (status, task_title)))

    def update_telemetry(self, gpu_text: str):
        self.log_queue.put(("telemetry", gpu_text))

    def show_warning(self, msg: str):
        self.log_queue.put(("warning", msg))

    def set_locked(self, locked: bool, reason: str = ""):
        self.log_queue.put(("locked", (locked, reason)))

    def _process_queue(self):
        try:
            while not self.log_queue.empty():
                kind, data = self.log_queue.get_nowait()
                if kind == "expand":
                    self.start_animation(data)
                elif kind == "log":
                    self.log_text.insert(tk.END, data)
                    self.log_text.see(tk.END)
                elif kind == "status":
                    status, title = data
                    self.current_status = status.upper()
                    color = "#10b981" if self.current_status in ["ONLINE", "READY"] else ("#f59e0b" if self.current_status == "BUSY" else "#3b82f6")

                    # Update Full HUD labels
                    self.status_lbl.configure(text=self.current_status, fg=color)
                    self.status_dot.configure(fg=color)
                    if title:
                        self.task_lbl.configure(text=f"Task: {title}")

                    # Update Circular Logo Pip color
                    self.circle_canvas.itemconfig(self.orb_pip, fill=color)
                    self.circle_canvas.itemconfig(self.orb_ring, outline=color)

                    # Dynamic animation: Enlarge on BUSY, auto-minimise to circular logo after idle
                    if self.current_status == "BUSY":
                        self.start_animation(True)
                    elif self.current_status in ["ONLINE", "READY"]:
                        if self.root:
                            self.root.after(7000, self._auto_collapse_if_idle)

                elif kind == "telemetry":
                    self.telem_lbl.configure(text=data)
                elif kind == "warning":
                    self.status_lbl.configure(text="ALERT", fg="#ef4444")
                    self.status_dot.configure(fg="#ef4444")
                    self.circle_canvas.itemconfig(self.orb_pip, fill="#ef4444")
                    self.log_text.insert(tk.END, f"\n⚠️ [GATEWAY ALERT] {data}\n")
                    self.log_text.see(tk.END)
                    self.start_animation(True)
                elif kind == "locked":
                    locked, reason = data
                    if locked:
                        self.status_lbl.configure(text="LOCKED", fg="#dc2626")
                        self.status_dot.configure(fg="#dc2626")
                        self.circle_canvas.itemconfig(self.orb_pip, fill="#dc2626")
                        self.task_lbl.configure(text=f"NODE LOCKED: {reason or 'Administrative Lock'}")
                        self.log_text.insert(tk.END, f"\n🔒 [STATION LOCKED] {reason}\n")
                        self.start_animation(True)
                    else:
                        self.status_lbl.configure(text="READY", fg="#10b981")
                        self.status_dot.configure(fg="#10b981")
                        self.circle_canvas.itemconfig(self.orb_pip, fill="#10b981")
                        self.task_lbl.configure(text="Idle • Ready for tasks")
                        self.log_text.insert(tk.END, f"\n🔓 [STATION UNLOCKED]\n")
        except Exception:
            pass
        if self.root:
            self.root.after(100, self._process_queue)


def http_post_json(url: str, data: dict, timeout: float = 6.0) -> dict:
    """Sends JSON POST request using standard Python library."""
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
                 storage_url: str = "https://labg418pc12.tailc8c1f6.ts.net:8443",
                 ollama_url: str = "http://127.0.0.1:11434",
                 default_model: str = "deepseek-coder-v2:16b",
                 poll_interval: float = 6.0,
                 show_hud: bool = True):
        self.node_id = node_id
        self.gateway_url = gateway_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.storage_url = storage_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.default_model = default_model
        self.poll_interval = poll_interval
        self.show_hud = show_hud

        self.current_task_id = None
        self.is_running = True
        self.is_locked = False
        os.makedirs("./workspace", exist_ok=True)

        self.hud = None
        if self.show_hud and HAS_TK:
            try:
                if "DISPLAY" not in os.environ and sys.platform != "win32":
                    os.environ["DISPLAY"] = ":0"
                self.hud = OverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                self.hud.start_hud_thread()
                print(f"[✓] Floating Screen Overlay HUD activated on DISPLAY {os.environ.get('DISPLAY', ':0')}")
            except Exception as e:
                print(f"[!] Floating HUD note: {e}")

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

        # Update HUD telemetry string
        if self.hud:
            telem_str = f"GPU: {gpu['utilization_pct']}% | VRAM: {gpu['vram_used_mb']/1024:.1f}/{gpu['vram_total_mb']/1024:.0f} GB | {gpu['temperature_c']}°C"
            self.hud.update_telemetry(telem_str)

        cpu_pct = 5.0
        ram_pct = 15.0
        ram_used_gb = 16.0
        ram_total_gb = 128.0
        try:
            with open("/proc/loadavg", "r") as f:
                cpu_pct = min(100.0, float(f.read().split()[0]) * 10.0)
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                total = int([l for l in lines if "MemTotal" in l][0].split()[1])
                avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
                ram_total_gb = round(total / 1024 / 1024, 1)
                ram_used_gb = round((total - avail) / 1024 / 1024, 1)
                ram_pct = round(((total - avail) / total) * 100, 1)
        except Exception:
            pass

        return {
            "pc_id": self.node_id,
            "lab_id": "DGX-CLUSTER",
            "node_id": self.node_id,
            "name": f"DGX Spark {self.node_id}",
            "ip": "127.0.0.1",
            "status": status,
            "current_task_id": self.current_task_id,
            "cpu_percent": cpu_pct,
            "ram_percent": ram_pct,
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "gpu": gpu,
            "gpu_name": gpu.get("name", "NVIDIA DGX"),
            "gpu_percent": gpu.get("utilization_pct", 0.0),
            "gpu_temp": gpu.get("temperature_c", 0.0),
            "active_model": self.default_model,
            "capabilities": ["code_generation", "code_review", "data_analysis"],
            "active_window": self.get_active_window(),
            "idle_seconds": int(self.get_idle_seconds()),
            "client_type": "dgx",
            "os_platform": "linux",
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        }

    def execute_ollama_query(self, prompt: str) -> str:
        """Queries local Ollama instance for code generation with HUD log streaming."""
        print(f"\n[{self.node_id}] Querying local model: {self.default_model}...")
        if self.hud:
            self.hud.append_log(f"[{self.node_id}] Querying {self.default_model} on local GPU...\n")

        system_instruction = (
            "You are an expert autonomous software engineer executing tasks on an NVIDIA DGX node.\n"
            "Generate complete, robust, production-quality code to fulfill the user's request.\n"
            "If the request involves creating a script, module, or document, specify the target filename on the first line inside the code block as a comment (e.g. '# filename: utils.py' or '// filename: main.cpp').\n"
            "Always wrap your code in standard markdown code blocks (```python ... ```).\n"
            "Do NOT include file upload code, network synchronization, or destination URLs; the autonomous runtime environment automatically captures and synchronizes all generated artifacts."
        )

        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False
        }
        res = http_post_json(url, payload, timeout=180.0)
        resp_text = res.get("response", "")
        if self.hud and resp_text:
            self.hud.append_log(f"\n--- Output ---\n{resp_text[:500]}...\n")
        return resp_text

    def upload_to_i7_vault(self, file_path: str, task_id: str) -> str:
        """Uploads generated script to AEGIS PC Vault via curl."""
        if not os.path.exists(file_path):
            return "file_not_found"

        candidates = [self.storage_url, "https://labg418pc12.tailc8c1f6.ts.net:8443", "http://100.88.197.6:9080"]
        last_error = "unknown"
        for vault_base in candidates:
            if not vault_base:
                continue
            try:
                upload_url = f"{vault_base.rstrip('/')}/api/storage/{self.node_id}/upload/{task_id}"
                cmd = ["curl", "-s", "--max-time", "15", "-F", f"file=@{file_path}", "-F", "stage=outputs", upload_url]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if "stored_in_vault" in res.stdout:
                    return f"synced_to_vault ({vault_base})"
                last_error = res.stdout[:80] if res.stdout else "empty_response"
            except Exception as e:
                last_error = str(e)
        return f"vault_sync_failed: {last_error}"

    def extract_and_vault_files(self, stdout_log: str, prompt: str, task_id: str) -> list:
        """Extracts all code blocks, names them cleanly, saves locally, and auto-vaults each file."""
        saved_files = []
        task_dir = os.path.join("./workspace", task_id)
        os.makedirs(task_dir, exist_ok=True)

        pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\n(.*?)```", re.DOTALL)
        matches = pattern.findall(stdout_log)

        # Detect any filename mentioned in the prompt (e.g. math_utils.py)
        prompt_filenames = re.findall(r"\b([\w-]+\.(?:py|sh|json|sql|html|css|js|txt|md|yaml|yml|cpp|c|h|rs))\b", prompt, re.IGNORECASE)

        if matches:
            for idx, (lang, code) in enumerate(matches):
                code = code.strip()
                if not code:
                    continue

                ext = "py"
                if lang:
                    lang_lower = lang.lower().strip()
                    ext_map = {"python": "py", "bash": "sh", "shell": "sh", "sh": "sh", "json": "json", "sql": "sql", "html": "html", "javascript": "js", "cpp": "cpp", "c": "c", "rust": "rs", "markdown": "md"}
                    ext = ext_map.get(lang_lower, "py" if "def " in code or "import " in code else "txt")

                filename = None
                code_lines = code.splitlines()[:3]
                for line in code_lines:
                    fn_match = re.search(r"(?:#|//|<!--|\*)\s*(?:filename:?\s*|file:?\s*)([\w-]+\.\w+)", line, re.IGNORECASE)
                    if fn_match:
                        filename = fn_match.group(1).strip()
                        break
                    fn_match2 = re.search(r"^[#//\s]+([\w-]+\.(?:py|sh|json|sql|html|css|js|txt))\b", line.strip(), re.IGNORECASE)
                    if fn_match2:
                        filename = fn_match2.group(1).strip()
                        break

                if not filename and idx < len(prompt_filenames):
                    filename = prompt_filenames[idx]

                if not filename:
                    filename = f"module_{idx + 1}.{ext}" if len(matches) > 1 else f"solution.{ext}"

                file_path = os.path.join(task_dir, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)

                vault_res = self.upload_to_i7_vault(file_path, task_id)
                print(f"[✓] Auto-Vault: {filename} -> {vault_res}")
                if self.hud:
                    self.hud.append_log(f"[✓] Auto-Vault: {filename} -> {vault_res}\n")

                saved_files.append((filename, file_path, vault_res))
        else:
            text_file = os.path.join(task_dir, "output.txt")
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(stdout_log)
            vault_res = self.upload_to_i7_vault(text_file, task_id)
            saved_files.append(("output.txt", text_file, vault_res))

        return saved_files

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

        if self.hud:
            self.hud.update_status("BUSY", task_title=prompt)
            self.hud.append_log(f"\n>>> [TASK {task_id}] Received from Gateway:\nPrompt: {prompt}\n")

        # 1. Run inference on local GPU with hidden autonomous directive
        stdout_log = self.execute_ollama_query(prompt)

        # 2. Extract all code files and silently auto-vault them to the Central PC Vault
        vaulted_records = self.extract_and_vault_files(stdout_log, prompt, task_id)

        # 3. Report completion back to Raspberry Pi Gateway
        complete_payload = {
            "task_id": task_id,
            "node_id": self.node_id,
            "exit_code": 0,
            "stdout": stdout_log[:1500],
            "stderr": "",
            "vaulted_files": [r[0] for r in vaulted_records],
            "vault_status": vaulted_records[0][2] if vaulted_records else "none",
            "drive_status": "not_requested"
        }

        for gw in [self.gateway_url, self.fallback_url]:
            res = http_post_json(f"{gw}/api/dgx/complete", complete_payload, timeout=6.0)
            if "status" in res:
                print(f"[✓] Task completion reported to {gw}")
                break

        self.current_task_id = None
        if self.hud:
            status_text = "LOCKED" if self.is_locked else "ONLINE"
            self.hud.update_status(status_text, task_title="Idle")
            self.hud.append_log(f"[Task {task_id} Complete - Ready for next heartbeat]\n")
        print(f"[{self.node_id}] Ready for next reverse heartbeat.\n")

    def handle_command(self, cmd: dict):
        cmd_id = cmd.get("command_id", f"cmd-{int(time.time())}")
        cmd_type = cmd.get("command_type")
        payload = cmd.get("payload", {})

        print(f"\n[{self.node_id}] INCOMING COMMAND: {cmd_type} ({cmd_id})")

        if cmd_type == "warn":
            msg = payload.get("message", "Operator alert")
            print(f"\n⚠️  [GATEWAY ALERT] {msg}\n")
            if self.hud:
                self.hud.show_warning(msg)

        elif cmd_type == "lock":
            reason = payload.get("reason", "Locked by operator")
            self.is_locked = True
            print(f"🔒 [LOCKED] {reason}")
            if self.hud:
                self.hud.set_locked(True, reason)

        elif cmd_type == "unlock":
            self.is_locked = False
            print(f"🔓 [UNLOCKED] Resumed normal operations.")
            if self.hud:
                self.hud.set_locked(False)

        elif cmd_type == "pull_model":
            model_name = payload.get("model", self.default_model)
            print(f"[*] Pulling Ollama model: {model_name}...")
            if self.hud:
                self.hud.append_log(f"[*] Pulling Ollama model: {model_name}...\n")
            subprocess.run(["ollama", "pull", model_name])

        elif cmd_type == "run_command":
            cmd_str = payload.get("command", "")
            print(f"[*] Running shell command: {cmd_str}")
            if self.hud:
                self.hud.append_log(f"[*] Executing: {cmd_str}\n")
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
        print(f" Floating HUD:  {'ACTIVE' if self.hud else 'DISABLED'}")
        print("=" * 65)

        gateways = [self.gateway_url, self.fallback_url]

        while self.is_running:
            telem = self.build_telemetry()
            for gw in gateways:
                # Try Pi /api/heartbeat first, fallback to /api/client/heartbeat
                for ep in ["/api/heartbeat", "/api/client/heartbeat"]:
                    res = http_post_json(f"{gw}{ep}", telem, timeout=15.0)
                    if "error" in res and "405" in res["error"]:
                        continue  # Wrong endpoint method, try next
                    if "error" in res and "timed out" in res["error"]:
                        # Normal long-polling cycle completed
                        break

                    # 1. Pi Gateway format: {"status": "ok", "command": ...}
                    cmd = res.get("command")
                    if cmd:
                        if isinstance(cmd, dict):
                            self.handle_command(cmd)
                        elif isinstance(cmd, str):
                            # Try parsing as JSON command
                            try:
                                parsed = json.loads(cmd)
                                if isinstance(parsed, dict) and "command_type" in parsed:
                                    self.handle_command(parsed)
                                    break
                            except Exception:
                                pass

                            # Check for simple supervisor commands
                            if cmd.startswith("warn:"):
                                self.handle_command({"command_type": "warn", "payload": {"message": cmd[5:].strip()}})
                            elif cmd in ["lock", "lock:now"]:
                                self.handle_command({"command_type": "lock", "payload": {"reason": "Remote lock"}})
                            elif cmd in ["unlock", "unlock:now"]:
                                self.handle_command({"command_type": "unlock", "payload": {}})
                            else:
                                # String prompt to execute on local GPU!
                                print(f"[{self.node_id}] Received prompt task from Gateway: {cmd}")
                                self.execute_task({"prompt": cmd, "task_id": f"tsk_{int(time.time())}"})
                        break
                    elif res.get("status") == "acknowledged":
                        if res.get("has_command"):
                            self.handle_command(res["command"])
                        elif res.get("has_task"):
                            self.execute_task(res["task"])
                        break
                    elif res.get("status") == "ok":
                        # Successful heartbeat, no pending command
                        break

            time.sleep(self.poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Standalone DGX Spark Node Agent with Floating HUD")
    parser.add_argument("--id", default="dgx-node-1", help="Node ID (e.g., dgx-node-1)")
    parser.add_argument("--gateway", default="https://raspberrypi.tailc8c1f6.ts.net", help="Raspberry Pi Tailscale Gateway")
    parser.add_argument("--storage", default="https://labg418pc12.tailc8c1f6.ts.net:8443", help="AEGIS PC Vault URL")
    parser.add_argument("--model", default="deepseek-coder-v2:16b", help="Local Ollama model name")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds")
    parser.add_argument("--no-hud", action="store_true", help="Disable desktop screen overlay HUD")
    args = parser.parse_args()

    agent = DGXStandaloneAgent(
        node_id=args.id,
        gateway_url=args.gateway,
        storage_url=args.storage,
        default_model=args.model,
        poll_interval=args.interval,
        show_hud=not args.no_hud
    )
    try:
        agent.start_polling()
    except KeyboardInterrupt:
        print("\nAgent stopped.")
