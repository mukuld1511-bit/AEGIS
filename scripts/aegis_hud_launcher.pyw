"""AEGIS Desktop HUD Standalone Launcher (Parakeet AI Neon Green Edition).
Runs silently without any terminal window using pythonw.exe.
Connects to local AEGIS Coordinator WebSocket (ws://127.0.0.1:9000/ws/cluster),
receives live cluster telemetry from DGX nodes, and runs the Dynamic Island HUD.
"""
import sys
import os
import json
import time
import asyncio
import threading
import websockets
import urllib.request

# Ensure workspace root is in path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt5.QtWidgets import QApplication
from aegis_node.overlay.dynamic_hud import AegisMasterHUD

def coordinator_listener_worker(hud: AegisMasterHUD):
    """Background thread that connects to AEGIS WebSocket and pipes live logs & telemetry to HUD."""
    ws_url = "ws://127.0.0.1:9000/ws/cluster"
    print(f"[*] HUD Worker connecting to {ws_url}...")

    async def ws_loop():
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    hud.append_log("[✓] Connected to Central Coordinator stream.\n")
                    while True:
                        raw = await ws.recv()
                        try:
                            msg = json.loads(raw)
                            event = msg.get("event")
                            data = msg.get("data", {})

                            if event == "node_telemetry_updated":
                                nid = data.get("node_id", "")
                                gpu = data.get("gpu", {})
                                if gpu:
                                    telem = f"GPU: {gpu.get('utilization_pct', 0):.0f}% | VRAM: {gpu.get('vram_used_mb', 0)/1024:.1f}/{gpu.get('vram_total_mb', 0)/1024:.0f} GB | {gpu.get('temperature_c', 0):.0f}°C"
                                    hud.update_telemetry(telem)
                            elif event == "task_created":
                                task_id = data.get("task_id", "")
                                node_id = data.get("assigned_node_id", "dgx-node-1")
                                prompt = data.get("prompt", "")
                                hud.update_status("BUSY", f"[{node_id}] {prompt[:50]}")
                                hud.append_log(f"\n⚡ [NEW TASK] {task_id} -> {node_id}\nPrompt: {prompt}\n", "neon")
                            elif event == "review_task_queued":
                                rev = data.get("reviewer_node", "dgx-node-2")
                                task = data.get("task", {})
                                hud.update_status("BUSY", f"[{rev}] Reviewing code & generating pytest...")
                                hud.append_log(f"\n⚛ [COLLABORATIVE HANDOFF] Code complete! Auto-routed to {rev} for QA review & pytest unit tests.\n", "cyan")
                            elif event == "dgx_task_finished":
                                nid = data.get("node_id", "")
                                tid = data.get("task_id", "")
                                hud.update_status("ONLINE", "Task Complete • Ready")
                                hud.append_log(f"\n[✓] {nid} finished {tid} successfully.\n", "green")
                            elif event == "task_step_updated":
                                stdout = data.get("stdout", "")
                                if stdout:
                                    hud.append_log(stdout)
                        except Exception:
                            pass
            except Exception:
                # Retry connection in 3 seconds
                await asyncio.sleep(3.0)

    # Run asyncio loop in worker thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_loop())

def main():
    hud = AegisMasterHUD(node_id="dgx-cluster", node_name="AEGIS Spark Cluster")
    hud.run_main_loop(lambda: coordinator_listener_worker(hud))

if __name__ == "__main__":
    main()
