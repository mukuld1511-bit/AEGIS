"""AEGIS DGX Desktop Screen Overlay HUD.
Floating, semi-transparent status head-up-display for physical screens attached to DGX machines.
Shows genuine terminal activity, GPU load, active LLM model, and node status.
"""
import sys
import tkinter as tk
from tkinter import font
import threading
import queue

class OverlayHUD:
    def __init__(self, node_id: str = "dgx-node-1", node_name: str = "DGX Spark 01"):
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()
        self.root = None

    def start_hud_thread(self):
        """Starts the HUD in a background daemon thread."""
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        try:
            self.root = tk.Tk()
            self.root.title(f"AEGIS - {self.node_id}")
            self.root.overrideredirect(True) # Borderless window
            self.root.attributes("-topmost", True) # Keep on top of screen
            
            # Position at top right
            screen_width = self.root.winfo_screenwidth()
            hud_width = 440
            hud_height = 280
            pos_x = screen_width - hud_width - 24
            pos_y = 24
            self.root.geometry(f"{hud_width}x{hud_height}+{pos_x}+{pos_y}")

            # Styling
            bg_dark = "#0c0e14"
            fg_cyan = "#00f0ff"
            fg_dim = "#7b88a1"
            card_bg = "#151821"

            self.root.configure(bg=bg_dark)

            # Container
            container = tk.Frame(self.root, bg=bg_dark, highlightbackground="#00f0ff", highlightthickness=1)
            container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

            # Header Frame
            hdr = tk.Frame(container, bg=card_bg, height=36)
            hdr.pack(fill=tk.X, padx=4, pady=4)

            self.status_dot = tk.Label(hdr, text="●", fg="#10b981", bg=card_bg, font=("Consolas", 12))
            self.status_dot.pack(side=tk.LEFT, padx=(8, 4))

            title_lbl = tk.Label(hdr, text=f"AEGIS :: {self.node_name}", fg="#ffffff", bg=card_bg, font=("Helvetica", 10, "bold"))
            title_lbl.pack(side=tk.LEFT)

            self.status_lbl = tk.Label(hdr, text="READY", fg="#10b981", bg=card_bg, font=("Helvetica", 9, "bold"))
            self.status_lbl.pack(side=tk.RIGHT, padx=8)

            # Telemetry Bar
            self.telem_lbl = tk.Label(
                container,
                text="GPU: 2% | VRAM: 4.1/80 GB | Temp: 38°C",
                fg=fg_cyan,
                bg=bg_dark,
                font=("Consolas", 8)
            )
            self.telem_lbl.pack(anchor="w", padx=8, pady=(2, 0))

            # Task info
            self.task_lbl = tk.Label(
                container,
                text="Active Task: Waiting for coordinator assignment...",
                fg=fg_dim,
                bg=bg_dark,
                font=("Helvetica", 8, "italic"),
                wraplength=420,
                justify="left"
            )
            self.task_lbl.pack(anchor="w", padx=8, pady=(2, 4))

            # Terminal log display area
            self.log_text = tk.Text(
                container,
                bg="#06070a",
                fg="#a7f3d0",
                font=("Consolas", 8),
                height=10,
                wrap="char",
                borderwidth=0,
                highlightthickness=0
            )
            self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
            self.log_text.insert(tk.END, f"AEGIS Node Agent Online.\nListening on private cluster bus...\n")

            # Periodic update loop
            self.root.after(100, self._process_queue)
            self.root.mainloop()
        except Exception as e:
            print(f"[OverlayHUD] GUI error: {e}")

    def append_log(self, text: str):
        """Thread-safe log append."""
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
                if kind == "log":
                    self.log_text.insert(tk.END, data)
                    self.log_text.see(tk.END)
                elif kind == "status":
                    status, title = data
                    color = "#10b981" if status.upper() in ["ONLINE", "READY"] else ("#f59e0b" if status.upper() == "BUSY" else "#3b82f6")
                    self.status_lbl.configure(text=status.upper(), fg=color)
                    self.status_dot.configure(fg=color)
                    if title:
                        self.task_lbl.configure(text=f"Task: {title}")
                elif kind == "telemetry":
                    self.telem_lbl.configure(text=data)
                elif kind == "warning":
                    self.status_lbl.configure(text="ALERT", fg="#ef4444")
                    self.status_dot.configure(fg="#ef4444")
                    self.log_text.insert(tk.END, f"\n⚠️ [GATEWAY ALERT] {data}\n")
                    self.log_text.see(tk.END)
                elif kind == "locked":
                    locked, reason = data
                    if locked:
                        self.status_lbl.configure(text="LOCKED", fg="#dc2626")
                        self.status_dot.configure(fg="#dc2626")
                        self.task_lbl.configure(text=f"NODE LOCKED: {reason or 'Administrative Lock'}")
                        self.log_text.insert(tk.END, f"\n🔒 [STATION LOCKED] {reason}\n")
                    else:
                        self.status_lbl.configure(text="READY", fg="#10b981")
                        self.status_dot.configure(fg="#10b981")
                        self.task_lbl.configure(text="Waiting for coordinator assignment...")
                        self.log_text.insert(tk.END, f"\n🔓 [STATION UNLOCKED]\n")
                    self.log_text.see(tk.END)
        except Exception:
            pass
        if self.root:
            self.root.after(100, self._process_queue)

