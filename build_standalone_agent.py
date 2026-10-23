import os
import sys
import re
import py_compile

with open("aegis_node/overlay/dynamic_hud.py", "r", encoding="utf-8") as f:
    hud_code = f.read()

with open("aegis_node/dgx_agent.py", "r", encoding="utf-8") as f:
    agent_code = f.read()

# 1. Extract HUD parts: from NODE_PASTEL_THEMES to AegisMasterHUD
match = re.search(r"(# ── Dynamic Curated Pastel Palettes per Node.*)", hud_code, re.DOTALL)
if not match:
    raise Exception("Could not find pastel palettes in dynamic_hud.py")
hud_classes = match.group(1).strip()

# In AegisMasterHUD, ensure set_expanded and toggle_expand exist
if "def set_expanded" not in hud_classes:
    expand_helper = """
    def set_expanded(self, expand: bool):
        self.log_queue.put(("expand", expand))

    def toggle_expand(self):
        self.log_queue.put(("toggle", None))
"""
    hud_classes += expand_helper

# In DynamicIslandWidget, ensure handling of expand and toggle in _process_queue
if 'kind == "expand"' not in hud_classes:
    hud_classes = hud_classes.replace(
        'elif kind == "telemetry":',
        '''elif kind == "expand":
                if data:
                    self.transition_to(self.STATE_EXPANDED)
                else:
                    self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
            elif kind == "toggle":
                self._toggle_expanded()
            elif kind == "telemetry":'''
    )

# 2. Extract OverlayHUD (Tkinter) from agent_code
overlay_match = re.search(r"(class OverlayHUD:.*?)(?=def http_post_json)", agent_code, re.DOTALL)
if not overlay_match:
    raise Exception("Could not find class OverlayHUD in dgx_agent.py")
overlay_tk_class = overlay_match.group(1).strip()

# 3. Extract from def http_post_json down to right before if __name__ == '__main__':
core_match = re.search(r"(def http_post_json\(.*?)(?=if __name__ == \"__main__\":)", agent_code, re.DOTALL)
if not core_match:
    raise Exception("Could not find http_post_json and DGXStandaloneAgent in dgx_agent.py")
core_agent_classes = core_match.group(1).strip()

# In DGXStandaloneAgent.__init__, update the HUD initialization so it uses AegisMasterHUD directly
old_hud_init = re.search(r"self\.hud = None\s+if self\.show_hud:.*?(?=\s+def get_gpu_metrics)", core_agent_classes, re.DOTALL)
if not old_hud_init:
    raise Exception("Could not find HUD init block in DGXStandaloneAgent")

new_hud_init = """self.hud = None
        if self.show_hud:
            try:
                if HAS_PYQT:
                    try:
                        self.hud = AegisMasterHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                        print(f"[✓] AEGIS Apple-Style Pastel Dynamic Island & Corner HUD active on DISPLAY {os.environ.get('DISPLAY', ':0')}")
                    except Exception as e:
                        print(f"[!] PyQt5 HUD error ({e}), trying Tkinter...")
                        if HAS_TK:
                            self.hud = OverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                            self.hud.start_hud_thread()
                elif HAS_TK:
                    self.hud = OverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                    self.hud.start_hud_thread()
                    print(f"[✓] Tkinter Glass HUD activated on DISPLAY {os.environ.get('DISPLAY', ':0')}")
                else:
                    print("[!] No GUI library available for HUD. Running in headless mode.")
            except Exception as e:
                print(f"[!] Floating HUD note: {e}")"""

core_agent_classes = core_agent_classes[:old_hud_init.start()] + new_hud_init + core_agent_classes[old_hud_init.end():]

# 4. Construct complete header
header = '''#!/usr/bin/env python3
"""AEGIS Standalone DGX Spark Node Agent with Apple-Style Pastel Dynamic Island HUD (dgx_agent.py).
Zero External Dependencies (Self-contained single-file agent + dynamic desktop overlay).
- Minimal Apple-style Dynamic Island Notch (compact idle pill -> stretched live activity -> expanded hub).
- Curated soft pastel color palette per DGX node (Lavender for Node 1, Sky for Node 2, Mint for Node 3, etc.).
- Floating Minimal Corner Glass Orb (bottom-right 64x64 animated atom).
- Outbound polling every 6 seconds to Raspberry Pi Gateway (https://raspberrypi.tailc8c1f6.ts.net).
- Zero inbound open ports required (100% firewall / NAT traversal).
- Live NVIDIA GPU telemetry (utilization, VRAM used/total, temp).
- Runs local Ollama LLM (qwen2.5-coder:32b, llama3.3:70b, deepseek-coder-v2).
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
from typing import Optional, Dict, Any, List, Union

# Auto-configure X11 Display & Authority for DGX / Linux GUI HUD
if sys.platform != "win32":
    if not os.environ.get("DISPLAY"):
        for disp in [":0", ":1", ":2"]:
            if os.path.exists(f"/tmp/.X11-unix/X{disp.replace(':', '')}"):
                os.environ["DISPLAY"] = disp
                break
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":0"

    if not os.environ.get("XAUTHORITY"):
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        possible_auths = [
            os.path.expanduser("~/.Xauthority"),
            f"/run/user/{uid}/gdm/Xauthority",
            f"/run/user/{uid}/gdm3/Xauthority",
            f"/run/user/{uid}/Xauthority"
        ]
        for xauth in possible_auths:
            if xauth and os.path.exists(xauth):
                os.environ["XAUTHORITY"] = xauth
                break
    try:
        subprocess.run(["xhost", "+local:"], capture_output=True, timeout=1.0)
    except Exception:
        pass

# Optional GUI Frameworks for Desktop HUD (Prefer PyQt5 for true 32-bit ARGB glassmorphic dynamic island; fallback to Tkinter)
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QRectF, pyqtSignal, QObject
    from PyQt5.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, 
        QLinearGradient, QPainterPath, QCursor, QFontMetrics
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QTextEdit, QFrame, QPushButton, QComboBox,
        QSlider, QCheckBox, QStackedWidget, QTabWidget, QGraphicsDropShadowEffect
    )
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

try:
    import tkinter as tk
    HAS_TK = True
except ImportError:
    HAS_TK = False
'''

# 5. Construct __main__ block with bulletproof args & background logging
main_block = '''if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Standalone DGX Spark Node Agent with Pastel Dynamic Island HUD")
    parser.add_argument("--id", default="dgx-node-1", help="Node ID (e.g., dgx-node-1, dgx-node-2, dgx-node-3)")
    parser.add_argument("--gateway", default="https://labg418pc12.tailc8c1f6.ts.net", help="AEGIS Central Coordinator Gateway")
    parser.add_argument("--storage", default="https://labg418pc12.tailc8c1f6.ts.net:8443", help="AEGIS PC Vault URL")
    parser.add_argument("--model", default=os.environ.get("AEGIS_MODEL", "qwen2.5-coder:32b"), help="Local Ollama model name (e.g. qwen2.5-coder:32b, llama3.3:70b)")
    parser.add_argument("--ctx", type=int, default=int(os.environ.get("AEGIS_NUM_CTX", "65536")), help="Context window token limit (default: 65536, up to 131072)")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds")
    parser.add_argument("--hud", action="store_true", default=True, help="Enable desktop screen overlay HUD (enabled by default)")
    parser.add_argument("--no-hud", action="store_true", help="Disable desktop screen overlay HUD")
    parser.add_argument("--background", "-b", "--detach", action="store_true", help="Run agent completely in the background without exposed terminal")
    args, unknown = parser.parse_known_args()

    # If --background or -b or --detach is requested, spawn detached background daemon and log to ~/aegis_agent.log
    if (args.background or os.environ.get("AEGIS_BACKGROUND") == "1") and not os.environ.get("_AEGIS_DETACHED"):
        env = os.environ.copy()
        env["_AEGIS_DETACHED"] = "1"
        log_path = os.path.expanduser("~/aegis_agent.log")
        log_file = open(log_path, "a", encoding="utf-8")
        clean_args = [a for a in sys.argv[1:] if a not in ["--background", "-b", "--detach"]]
        cmd = [sys.executable, os.path.abspath(__file__)] + clean_args
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            **kwargs
        )
        print("=" * 65)
        print(f" [✓] AEGIS Agent ({args.id}) launched in BACKGROUND (PID: {proc.pid})")
        print(f" [✓] Apple-Style Pastel Dynamic Island HUD active on DISPLAY {os.environ.get('DISPLAY', ':0')}")
        print(f" [✓] Live agent log streaming to: {log_path}")
        print(f" [✓] Terminal can now be safely CLOSED without stopping the agent.")
        print("=" * 65)
        sys.exit(0)

    agent = DGXStandaloneAgent(
        node_id=args.id,
        gateway_url=args.gateway,
        storage_url=args.storage,
        default_model=args.model,
        default_num_ctx=args.ctx,
        poll_interval=args.interval,
        show_hud=not args.no_hud
    )
    try:
        agent.start_polling()
    except KeyboardInterrupt:
        print("\\nAgent stopped.")
'''

full_agent = f"{header}\n\n{hud_classes}\n\n{overlay_tk_class}\n\n{core_agent_classes}\n\n{main_block}\n"

with open("aegis_node/dgx_agent.py", "w", encoding="utf-8") as f:
    f.write(full_agent)

import shutil
shutil.copy2("aegis_node/dgx_agent.py", "aegis_storage_vault/dgx_agent.py")

print(f"Successfully generated aegis_node/dgx_agent.py and synced to aegis_storage_vault/dgx_agent.py ({len(full_agent.splitlines())} lines).")
py_compile.compile("aegis_node/dgx_agent.py", doraise=True)
print("Syntax verification passed with ZERO errors!")
