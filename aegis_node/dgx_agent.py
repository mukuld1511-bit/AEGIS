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
import ctypes
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

class X11WindowShaper:
    """True Circular & Rounded-Rect window mask for X11 on Linux using XShape extension."""
    def __init__(self):
        self.available = False
        try:
            self.X11 = ctypes.CDLL("libX11.so.6")
            self.Xext = ctypes.CDLL("libXext.so.6")
            self.available = True
        except Exception:
            try:
                self.X11 = ctypes.CDLL("libX11.so")
                self.Xext = ctypes.CDLL("libXext.so")
                self.available = True
            except Exception:
                self.available = False

    def shape_circle(self, x11_window_id: int, diameter: int):
        if not self.available or not x11_window_id:
            return False
        try:
            display = self.X11.XOpenDisplay(None)
            if not display:
                return False

            class XRectangle(ctypes.Structure):
                _fields_ = [
                    ("x", ctypes.c_short),
                    ("y", ctypes.c_short),
                    ("width", ctypes.c_ushort),
                    ("height", ctypes.c_ushort)
                ]

            r = diameter / 2.0
            rects = []
            for y in range(diameter):
                dy = abs(y + 0.5 - r)
                if dy <= r:
                    dx = math.sqrt(max(0.0, r * r - dy * dy))
                    x_start = int(round(r - dx))
                    x_end = int(round(r + dx))
                    rects.append(XRectangle(x_start, y, max(1, x_end - x_start), 1))

            rect_array = (XRectangle * len(rects))(*rects)
            self.Xext.XShapeCombineRectangles(display, x11_window_id, 0, 0, 0, rect_array, len(rects), 0, 0)
            self.X11.XFlush(display)
            self.X11.XCloseDisplay(display)
            return True
        except Exception:
            return False

    def reset_shape(self, x11_window_id: int, width: int, height: int, radius: int = 18):
        if not self.available or not x11_window_id:
            return False
        try:
            display = self.X11.XOpenDisplay(None)
            if not display:
                return False

            class XRectangle(ctypes.Structure):
                _fields_ = [
                    ("x", ctypes.c_short),
                    ("y", ctypes.c_short),
                    ("width", ctypes.c_ushort),
                    ("height", ctypes.c_ushort)
                ]

            rects = []
            for y in range(height):
                if y < radius:
                    dy = radius - (y + 0.5)
                    dx = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
                    x_start = int(round(dx))
                    x_end = width - int(round(dx))
                    rects.append(XRectangle(x_start, y, max(1, x_end - x_start), 1))
                elif y >= height - radius:
                    dy = (y + 0.5) - (height - radius)
                    dx = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
                    x_start = int(round(dx))
                    x_end = width - int(round(dx))
                    rects.append(XRectangle(x_start, y, max(1, x_end - x_start), 1))
                else:
                    rects.append(XRectangle(0, y, width, 1))

            rect_array = (XRectangle * len(rects))(*rects)
            self.Xext.XShapeCombineRectangles(display, x11_window_id, 0, 0, 0, rect_array, len(rects), 0, 0)
            self.X11.XFlush(display)
            self.X11.XCloseDisplay(display)
            return True
        except Exception:
            return False

class OverlayHUD:
    """Floating Transparent Glassmorphic HUD with glowing Purple Atom Motif:
    - Large 3D translucent frosted glass orb (100px) with true X11 circular masking.
    - Luminous purple atomic orbitals with rotating electrons & glowing nucleus.
    - Damped spring-elastic expansion into a large, spacious glassmorphic console (620x430).
    - Inset frosted glass panels, glowing telemetry, and real-time code stream.
    """
    def __init__(self, node_id: str = "dgx-node-1", node_name: str = "DGX Spark 01"):
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()
        self.root = None
        self.shaper = X11WindowShaper()
        self.is_expanded = False
        self.is_animating = False
        self.current_status = "ONLINE"
        self.pulse_phase = False
        self.atom_phase = 0.0

        # Bigger UI element dimensions
        self.circle_size = 100
        self.full_width = 620
        self.full_height = 430
        self.pos_y = 24
        self.screen_width = 1920
        self._drag_x = 0
        self._drag_y = 0
        self.orbits = [-30, 30, 90]

    def start_hud_thread(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        try:
            self.root = tk.Tk()
            self.root.title(f"AEGIS - {self.node_id}")
            self.root.overrideredirect(True) # Borderless floating window
            self.root.attributes("-topmost", True) # Always on top

            # Translucent Frosted Glass Palette (Soft lavender mist / translucent white glass)
            glass_canvas = "#f5f3ff"     # Translucent lavender glass canvas
            glass_card = "#ffffff"       # Frosted glass card
            glass_border = "#c4b5fd"     # Specular glass rim
            recessed_tray = "#ffffff"    # Frosted glass trough
            text_primary = "#0f172a"     # Crisp charcoal text
            text_secondary = "#334155"   # Dark slate
            text_muted = "#64748b"       # Soft slate subtext
            accent_purple = "#7c3aed"    # Radiant purple / violet (from Atom motif)
            accent_lavender = "#ede9fe"  # Frosted lavender badge pill

            self.root.configure(bg=glass_canvas)
            try:
                self.root.attributes("-alpha", 0.86)
            except Exception:
                pass

            self.screen_width = self.root.winfo_screenwidth()
            pos_x_mini = self.screen_width - self.circle_size - 28
            self.root.geometry(f"{self.circle_size}x{self.circle_size}+{pos_x_mini}+{self.pos_y}")
            self.root.update_idletasks()

            # Apply X11 True Circular Mask on Linux (Physically removes square corners!)
            try:
                self.shaper.shape_circle(self.root.winfo_id(), self.circle_size)
            except Exception:
                pass

            # Outer container
            self.main_container = tk.Frame(self.root, bg=glass_canvas)
            self.main_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

            # ========================================================
            # 1. 3D TRANSPARENT GLASS ORB WITH PURPLE ATOM (Idle State)
            # ========================================================
            self.circle_canvas = tk.Canvas(
                self.main_container,
                width=self.circle_size,
                height=self.circle_size,
                bg=glass_canvas,
                highlightthickness=0,
                cursor="hand2"
            )
            self.circle_canvas.pack(fill=tk.BOTH, expand=True)

            # Translucent Frosted Glass Disc (100px diameter)
            self.orb_body = self.circle_canvas.create_oval(2, 2, 98, 98, fill="#fdfcff", outline="#c4b5fd", width=1.5)

            # Specular Glass Gleam & Refraction Arc
            self.circle_canvas.create_arc(6, 6, 94, 94, start=45, extent=90, style="arc", outline="#ffffff", width=2.5)
            self.circle_canvas.create_oval(24, 6, 76, 24, fill="#ffffff", outline="")

            # Purple Atom Orbital Rings (Scaled up: a=32, b=12)
            cx, cy = 50, 50
            orbit_colors = ["#8b5cf6", "#9333ea", "#7c3aed"]
            for idx, angle_deg in enumerate(self.orbits):
                rad = math.radians(angle_deg)
                pts = []
                for step in range(48):
                    t = 2 * math.pi * step / 48.0
                    x = cx + 32 * math.cos(t) * math.cos(rad) - 12 * math.sin(t) * math.sin(rad)
                    y = cy + 32 * math.cos(t) * math.sin(rad) + 12 * math.sin(t) * math.cos(rad)
                    pts.extend([x, y])
                pts.extend([pts[0], pts[1]])
                self.circle_canvas.create_line(pts, fill=orbit_colors[idx], width=1.8, smooth=True)

            # Glowing Purple Nucleus Vortex (Multi-layer radiant corona)
            self.circle_canvas.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill="#ede9fe", outline="")  # Lavender corona
            self.circle_canvas.create_oval(cx - 8.5, cy - 8.5, cx + 8.5, cy + 8.5, fill="#c084fc", outline="")  # Lilac mid glow
            self.circle_canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#7c3aed", outline="")  # Deep violet core
            self.circle_canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#ffffff", outline="")  # Brilliant center star

            # Tactile Glass Status Pip (Gem Bead at bottom-right)
            self.circle_canvas.create_oval(67, 67, 87, 87, fill="#e9d5ff", outline="")
            self.orb_pip = self.circle_canvas.create_oval(68, 68, 86, 86, fill="#10b981", outline="#34d399", width=1.5)
            self.circle_canvas.create_oval(71, 70, 75, 74, fill="#ffffff", outline="")

            # Initial draw of revolving electrons
            self._update_atom_electrons()

            # Click circular glass orb to spring-expand
            self.circle_canvas.bind("<Button-1>", lambda e: self.start_animation(True))

            # ========================================================
            # 2. BIGGER TRANSPARENT GLASS CONSOLE (Expanded State)
            # ========================================================
            self.full_frame = tk.Frame(
                self.main_container,
                bg=glass_canvas,
                highlightbackground=glass_border,
                highlightthickness=1.5
            )

            # Frosted Glass Header (Height 44px)
            hdr = tk.Frame(self.full_frame, bg=glass_card, height=44)
            hdr.pack(fill=tk.X, padx=0, pady=0)

            atom_icon = tk.Label(hdr, text="⚛", fg=accent_purple, bg=glass_card, font=("Helvetica", 16, "bold"))
            atom_icon.pack(side=tk.LEFT, padx=(12, 6))

            title_lbl = tk.Label(hdr, text=f"AEGIS Studio  •  {self.node_name}", fg=text_primary, bg=glass_card, font=("Helvetica", 11, "bold"))
            title_lbl.pack(side=tk.LEFT)

            # Tactile Glass Pill Button for collapse [ — ]
            collapse_btn = tk.Label(
                hdr,
                text="  —  ",
                fg=text_muted,
                bg="#f1f5f9",
                cursor="hand2",
                font=("Helvetica", 10, "bold"),
                padx=10,
                pady=3,
                relief="flat",
                highlightbackground="#e2e8f0",
                highlightthickness=1
            )
            collapse_btn.pack(side=tk.RIGHT, padx=(4, 10))
            collapse_btn.bind("<Button-1>", lambda e: self.start_animation(False))

            # Rounded lavender glass status pill
            pill_frame = tk.Frame(hdr, bg=accent_lavender, padx=10, pady=3)
            pill_frame.pack(side=tk.RIGHT, padx=4)

            self.status_dot = tk.Label(pill_frame, text="●", fg="#10b981", bg=accent_lavender, font=("Helvetica", 9))
            self.status_dot.pack(side=tk.LEFT)

            self.status_lbl = tk.Label(pill_frame, text="ONLINE", fg=accent_purple, bg=accent_lavender, font=("Helvetica", 9, "bold"))
            self.status_lbl.pack(side=tk.LEFT, padx=(4, 0))

            # Body Container
            body = tk.Frame(self.full_frame, bg=glass_canvas)
            body.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

            # Frosted Glass Trough for Telemetry
            telem_box = tk.Frame(body, bg=recessed_tray, highlightbackground="#ddd6fe", highlightthickness=1)
            telem_box.pack(fill=tk.X, padx=0, pady=(0, 6))

            self.telem_lbl = tk.Label(
                telem_box,
                text="GPU 0%  •  VRAM 0.0/128 GB  •  35°C",
                fg=text_secondary,
                bg=recessed_tray,
                font=("Consolas", 10),
                pady=4
            )
            self.telem_lbl.pack(anchor="w", padx=8)

            # Task banner
            self.task_lbl = tk.Label(
                body,
                text="Idle • Ready for assignments",
                fg=text_muted,
                bg=glass_canvas,
                font=("Helvetica", 10),
                wraplength=580,
                justify="left"
            )
            self.task_lbl.pack(anchor="w", padx=2, pady=(0, 6))

            # Frosted Glass Code Console (Height 13 lines, 10pt font)
            self.log_text = tk.Text(
                body,
                bg=glass_card,
                fg=text_primary,
                insertbackground=accent_purple,
                selectbackground="#ddd6fe",
                selectforeground="#0f172a",
                font=("Consolas", 10),
                height=13,
                wrap="char",
                borderwidth=0,
                highlightthickness=1,
                highlightbackground="#ddd6fe"
            )
            self.log_text.pack(fill=tk.BOTH, expand=True)

            self.log_text.tag_configure("purple", foreground=accent_purple, font=("Consolas", 10, "bold"))
            self.log_text.tag_configure("green", foreground="#059669", font=("Consolas", 10, "bold"))
            self.log_text.tag_configure("red", foreground="#dc2626", font=("Consolas", 10, "bold"))
            self.log_text.tag_configure("amber", foreground="#d97706")
            self.log_text.tag_configure("muted", foreground="#64748b")

            self.log_text.insert(tk.END, "⚛ AEGIS Autonomous Agent Online.\n", "purple")
            self.log_text.insert(tk.END, "Connected via Reverse-Heartbeat to Gateway.\n", "muted")

            # Enable window dragging on both circular orb and header
            self._bind_drag(self.circle_canvas)
            self._bind_drag(hdr)

            # Start animation ticks and queue processor
            self.root.after(100, self._process_queue)
            self.root.after(70, self._atom_tick)
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

    def _update_atom_electrons(self):
        """Draws revolving electrons along the orbital tracks."""
        if not self.root or self.is_expanded:
            return
        self.circle_canvas.delete("atom_electron")
        cx, cy = 50, 50
        a, b = 32, 12
        for idx, angle_deg in enumerate(self.orbits):
            rad = math.radians(angle_deg)
            t_el = self.atom_phase + idx * (2 * math.pi / 3.0)
            x_el = cx + a * math.cos(t_el) * math.cos(rad) - b * math.sin(t_el) * math.sin(rad)
            y_el = cy + a * math.cos(t_el) * math.sin(rad) + b * math.sin(t_el) * math.cos(rad)
            # Electron lilac glow aura
            self.circle_canvas.create_oval(
                x_el - 5, y_el - 5, x_el + 5, y_el + 5,
                fill="#c084fc", outline="", tags="atom_electron"
            )
            # Electron brilliant white core
            self.circle_canvas.create_oval(
                x_el - 2.5, y_el - 2.5, x_el + 2.5, y_el + 2.5,
                fill="#ffffff", outline="", tags="atom_electron"
            )

    def _atom_tick(self):
        """Mesmerizing orbital motion for the purple atom motif."""
        if not self.root:
            return
        if not self.is_expanded and not self.is_animating:
            speed = 0.14 if self.current_status == "BUSY" else 0.06
            self.atom_phase = (self.atom_phase + speed) % (2 * math.pi)
            self._update_atom_electrons()
        self.root.after(70, self._atom_tick)

    def _pulse_loop(self):
        """Tactile gentle pulse on the glass bead status pip."""
        if not self.root:
            return
        if not self.is_expanded and not self.is_animating:
            self.pulse_phase = not self.pulse_phase
            base_col = "#10b981" if self.current_status in ["ONLINE", "READY"] else "#7c3aed"
            dim_col = "#059669" if self.current_status in ["ONLINE", "READY"] else "#5b21b6"
            cur = base_col if self.pulse_phase else dim_col
            self.circle_canvas.itemconfig(self.orb_pip, fill=cur)
        self.root.after(1200, self._pulse_loop)

    def toggle_expand(self):
        self.start_animation(not self.is_expanded)

    def set_expanded(self, expand: bool):
        self.log_queue.put(("expand", expand))

    def start_animation(self, target_expanded: bool):
        """Spring-elastic expansion / minimization between glass orb and console."""
        if self.is_animating or self.is_expanded == target_expanded:
            return

        self.is_animating = True
        self.target_expanded = target_expanded

        if target_expanded:
            try:
                self.shaper.reset_shape(self.root.winfo_id(), self.full_width, self.full_height, radius=18)
            except Exception:
                pass
            self.circle_canvas.pack_forget()
            self.full_frame.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.circle_size, self.circle_size
            end_w, end_h = self.full_width, self.full_height
        else:
            self.full_frame.pack_forget()
            self.circle_canvas.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.full_width, self.full_height
            end_w, end_h = self.circle_size, self.circle_size

        self._step_animation(1, 15, start_w, end_w, start_h, end_h)

    def _step_animation(self, step, total_steps, start_w, end_w, start_h, end_h):
        if not self.root:
            self.is_animating = False
            return

        t = step / float(total_steps)
        # Damped spring oscillation (soft tactile glass squish & settle)
        if step == total_steps:
            ease = 1.0
        else:
            ease = 1.0 - math.exp(-5.5 * t) * math.cos(3.8 * t)

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
            if not self.is_expanded:
                try:
                    self.shaper.shape_circle(self.root.winfo_id(), self.circle_size)
                except Exception:
                    pass
            else:
                border = "#7c3aed" if self.current_status == "BUSY" else ("#10b981" if self.current_status in ["ONLINE", "READY"] else "#c4b5fd")
                self.full_frame.configure(highlightbackground=border)

    def _auto_collapse_if_idle(self):
        if self.current_status in ["ONLINE", "READY"] and self.is_expanded:
            self.start_animation(False)

    def append_log(self, text: str, tag: str = ""):
        self.log_queue.put(("log", (text, tag)))

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
                    if isinstance(data, tuple):
                        text, tag = data
                        if tag:
                            self.log_text.insert(tk.END, text, tag)
                        else:
                            self.log_text.insert(tk.END, text)
                    else:
                        self.log_text.insert(tk.END, str(data))
                    self.log_text.see(tk.END)
                elif kind == "status":
                    status, title = data
                    self.current_status = status.upper()
                    color = "#10b981" if self.current_status in ["ONLINE", "READY"] else ("#7c3aed" if self.current_status == "BUSY" else "#3b82f6")

                    # Update Full HUD labels
                    self.status_lbl.configure(text=self.current_status, fg=color)
                    self.status_dot.configure(fg=color)
                    if title:
                        self.task_lbl.configure(text=f"Task: {title}")

                    # Update Circular Logo Pip color
                    self.circle_canvas.itemconfig(self.orb_pip, fill=color)

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
                    self.log_text.insert(tk.END, f"\n⚠️ [GATEWAY ALERT] {data}\n", "red")
                    self.log_text.see(tk.END)
                    self.start_animation(True)
                elif kind == "locked":
                    locked, reason = data
                    if locked:
                        self.status_lbl.configure(text="LOCKED", fg="#dc2626")
                        self.status_dot.configure(fg="#dc2626")
                        self.circle_canvas.itemconfig(self.orb_pip, fill="#dc2626")
                        self.task_lbl.configure(text=f"NODE LOCKED: {reason or 'Administrative Lock'}")
                        self.log_text.insert(tk.END, f"\n🔒 [STATION LOCKED] {reason}\n", "red")
                        self.start_animation(True)
                    else:
                        self.status_lbl.configure(text="ONLINE", fg="#10b981")
                        self.status_dot.configure(fg="#10b981")
                        self.circle_canvas.itemconfig(self.orb_pip, fill="#10b981")
                        self.task_lbl.configure(text="Idle • Ready for tasks")
                        self.log_text.insert(tk.END, f"\n🔓 [STATION UNLOCKED]\n", "green")
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
            self.hud.append_log(f"[{self.node_id}] Querying {self.default_model} on local GPU...\n", "purple")

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
                    self.hud.append_log(f"[✓] Auto-Vault: {filename} -> {vault_res}\n", "green")

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
            self.hud.append_log(f"\n>>> [TASK {task_id}] Received from Gateway:\nPrompt: {prompt}\n", "purple")

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
            self.hud.append_log(f"[Task {task_id} Complete - Ready for next heartbeat]\n", "green")
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
