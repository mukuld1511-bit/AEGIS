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

# Optional GUI Frameworks for Desktop HUD (Prefer PyQt5 for true 32-bit ARGB glassmorphic circular orb; fallback to Tkinter)
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QRectF
    from PyQt5.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, 
        QLinearGradient, QPainterPath, QCursor
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QTextEdit, QFrame
    )
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

try:
    import tkinter as tk
    HAS_TK = True
except ImportError:
    HAS_TK = False

if HAS_PYQT:
    class PyQtHUDWidget(QWidget):
        """Native 32-bit ARGB Floating Glassmorphic Animated Atom Orb HUD."""
        def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", shared_queue=None):
            super().__init__()
            self.node_id = node_id
            self.node_name = node_name
            self.log_queue = shared_queue or queue.Queue()
            self.is_expanded = False
            self.is_animating = False
            self.current_status = "ONLINE"
            self.atom_phase = 0.0
            self.pulse_phase = 0.0
            self.gpu_text = "GPU 0%  •  VRAM 0.0/128 GB  •  35°C"
            self.task_text = "Idle • Ready for assignments"

            # Dimensions
            self.mini_size = 92
            self.full_w = 580
            self.full_h = 420
            self.cur_w = self.mini_size
            self.cur_h = self.mini_size

            # Window properties
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setMouseTracking(True)

            screen = QApplication.primaryScreen().availableGeometry()
            self.margin_right = 24
            self.margin_top = 24
            self.right_edge = screen.x() + screen.width() - self.margin_right
            self.pos_x = self.right_edge - self.cur_w
            self.pos_y = screen.y() + self.margin_top
            self.setGeometry(self.pos_x, self.pos_y, self.cur_w, self.cur_h)

            # Dragging
            self._drag_active = False
            self._user_dragged = False
            self._drag_pos = QPoint()

            # Expanded UI
            self._init_expanded_ui()

            # Animation timer (60 FPS)
            self.anim_timer = QTimer(self)
            self.anim_timer.timeout.connect(self._animation_tick)
            self.anim_step = 0
            self.anim_total = 14

            # Orbit rotation & pulse timer (40 FPS)
            self.orbit_timer = QTimer(self)
            self.orbit_timer.timeout.connect(self._orbit_tick)
            self.orbit_timer.start(25)

            # Queue processor timer (30ms)
            self.q_timer = QTimer(self)
            self.q_timer.timeout.connect(self._process_queue)
            self.q_timer.start(30)

        def _init_expanded_ui(self):
            self.content_widget = QWidget(self)
            self.content_widget.setGeometry(10, 10, self.full_w - 20, self.full_h - 20)
            self.content_widget.setVisible(False)

            layout = QVBoxLayout(self.content_widget)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            # Header
            hdr = QHBoxLayout()
            self.lbl_title = QLabel(f"⚛  AEGIS Spark  •  {self.node_name}", self.content_widget)
            self.lbl_title.setStyleSheet("color: #1e1b4b; font-size: 13px; font-weight: bold;")
            hdr.addWidget(self.lbl_title)

            hdr.addStretch()

            self.lbl_status = QLabel("● ONLINE", self.content_widget)
            self.lbl_status.setStyleSheet("background: #ede9fe; color: #7c3aed; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 3px 8px;")
            hdr.addWidget(self.lbl_status)

            self.btn_collapse = QLabel(" — ", self.content_widget)
            self.btn_collapse.setStyleSheet("background: #f1f5f9; color: #64748b; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 2px 8px; border: 1px solid #e2e8f0;")
            self.btn_collapse.setCursor(QCursor(Qt.PointingHandCursor))
            self.btn_collapse.mousePressEvent = lambda e: self.start_animation(False)
            hdr.addWidget(self.btn_collapse)

            layout.addLayout(hdr)

            # Telemetry Pill
            self.lbl_telem = QLabel(self.gpu_text, self.content_widget)
            self.lbl_telem.setStyleSheet("background: #ffffff; color: #334155; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #ddd6fe; border-radius: 6px; padding: 5px 10px;")
            layout.addWidget(self.lbl_telem)

            # Task Text
            self.lbl_task = QLabel(self.task_text, self.content_widget)
            self.lbl_task.setStyleSheet("color: #64748b; font-size: 11px;")
            layout.addWidget(self.lbl_task)

            # Log Console
            self.log_console = QTextEdit(self.content_widget)
            self.log_console.setReadOnly(True)
            self.log_console.setLineWrapMode(QTextEdit.WidgetWidth)
            self.log_console.setStyleSheet("background: #ffffff; color: #0f172a; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #ddd6fe; border-radius: 8px; padding: 6px;")
            layout.addWidget(self.log_console)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            if not self.is_expanded and not self.is_animating:
                self._paint_circular_orb(painter)
            else:
                self._paint_glass_card(painter)

        def _paint_circular_orb(self, painter):
            w = self.width()
            h = self.height()
            cx = w / 2.0
            cy = h / 2.0
            r = (self.mini_size - 12) / 2.0

            # 1. Soft Frosted Clay/Glass Orb Background (Translucent light theme)
            grad = QRadialGradient(cx - r*0.3, cy - r*0.3, r * 1.3)
            grad.setColorAt(0.0, QColor(255, 255, 255, 235))
            grad.setColorAt(0.65, QColor(248, 246, 255, 215))
            grad.setColorAt(1.0, QColor(237, 233, 254, 195))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

            # 2. Specular Glass Rim Ring
            rim_color = QColor(196, 181, 253, 220) if self.current_status == "ONLINE" else QColor(124, 58, 237, 240)
            painter.setPen(QPen(rim_color, 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

            # 3. Dynamic 3-Orbit Purple Atom
            orbits = [-30.0, 30.0, 90.0]
            orbit_colors = [QColor(139, 92, 246, 190), QColor(147, 51, 234, 190), QColor(124, 58, 237, 200)]
            a = r * 0.68
            b = r * 0.28

            for idx, angle_deg in enumerate(orbits):
                rad = math.radians(angle_deg)
                cos_a = math.cos(rad)
                sin_a = math.sin(rad)

                path = QPainterPath()
                steps = 36
                for s in range(steps + 1):
                    t = 2 * math.pi * s / float(steps)
                    x = cx + a * math.cos(t) * cos_a - b * math.sin(t) * sin_a
                    y = cy + a * math.cos(t) * sin_a + b * math.sin(t) * cos_a
                    if s == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)

                painter.setPen(QPen(orbit_colors[idx], 1.4))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

                # Revolving electron dot on each orbit
                e_t = self.atom_phase + (idx * (2 * math.pi / 3.0))
                ex = cx + a * math.cos(e_t) * cos_a - b * math.sin(e_t) * sin_a
                ey = cy + a * math.cos(e_t) * sin_a + b * math.sin(e_t) * cos_a

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(192, 132, 252, 255)))
                painter.drawEllipse(QRectF(ex - 2.8, ey - 2.8, 5.6, 5.6))
                painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
                painter.drawEllipse(QRectF(ex - 1.2, ey - 1.2, 2.4, 2.4))

            # 4. Central Glowing Violet Nucleus
            nuc_grad = QRadialGradient(cx, cy, 7.0)
            nuc_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            nuc_grad.setColorAt(0.4, QColor(167, 139, 250, 240))
            nuc_grad.setColorAt(0.8, QColor(124, 58, 237, 220))
            nuc_grad.setColorAt(1.0, QColor(109, 40, 217, 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(nuc_grad))
            painter.drawEllipse(QRectF(cx - 7.0, cy - 7.0, 14.0, 14.0))

            # 5. Pulsing Status Pip
            pulse_alpha = int(180 + 75 * math.sin(self.pulse_phase))
            status_col = QColor(16, 185, 129, pulse_alpha) if self.current_status == "ONLINE" else QColor(124, 58, 237, pulse_alpha)
            pip_y = cy + r - 3.5
            painter.setBrush(QBrush(status_col))
            painter.drawEllipse(QRectF(cx - 3.5, pip_y, 7.0, 7.0))

        def _paint_glass_card(self, painter):
            w = float(self.width())
            h = float(self.height())
            rect = QRectF(4, 4, w - 8, h - 8)

            # Translucent Frosted Glass Card
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 240))
            grad.setColorAt(1.0, QColor(248, 246, 255, 230))

            border_col = QColor(196, 181, 253, 230) if self.current_status == "ONLINE" else QColor(124, 58, 237, 240)
            painter.setPen(QPen(border_col, 1.5))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(rect, 20.0, 20.0)

        def _orbit_tick(self):
            speed = 0.08 if self.current_status in ["BUSY", "COMPUTING"] else 0.04
            self.atom_phase = (self.atom_phase + speed) % (2 * math.pi)
            self.pulse_phase = (self.pulse_phase + 0.07) % (2 * math.pi)
            self.update()

        def start_animation(self, target_expanded: bool):
            if self.is_animating or self.is_expanded == target_expanded:
                return
            self.is_animating = True
            self.target_expanded = target_expanded
            self.anim_step = 0

            if target_expanded:
                self.content_widget.setVisible(False)
                self.start_w, self.start_h = self.mini_size, self.mini_size
                self.end_w, self.end_h = self.full_w, self.full_h
            else:
                self.content_widget.setVisible(False)
                self.start_w, self.start_h = self.full_w, self.full_h
                self.end_w, self.end_h = self.mini_size, self.mini_size

            self.anim_timer.start(16)

        def _animation_tick(self):
            self.anim_step += 1
            t = self.anim_step / float(self.anim_total)
            ease = 1.0 - math.pow(1.0 - t, 3)

            self.cur_w = int(self.start_w + (self.end_w - self.start_w) * ease)
            self.cur_h = int(self.start_h + (self.end_h - self.start_h) * ease)

            screen = QApplication.primaryScreen().availableGeometry()
            if not self._user_dragged:
                self.right_edge = screen.x() + screen.width() - self.margin_right
            pos_x = self.right_edge - self.cur_w
            self.setGeometry(pos_x, self.y(), self.cur_w, self.cur_h)

            if self.anim_step >= self.anim_total:
                self.anim_timer.stop()
                self.is_animating = False
                self.is_expanded = self.target_expanded
                if self.is_expanded:
                    self.content_widget.setGeometry(10, 10, self.cur_w - 20, self.cur_h - 20)
                    self.content_widget.setVisible(True)
                self.update()

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_active = True
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

        def mouseMoveEvent(self, event):
            if self._drag_active and (event.buttons() & Qt.LeftButton):
                new_pos = event.globalPos() - self._drag_pos
                self.move(new_pos)
                self.right_edge = new_pos.x() + self.cur_w
                self._user_dragged = True
                event.accept()

        def mouseReleaseEvent(self, event):
            if self._drag_active and event.button() == Qt.LeftButton:
                self._drag_active = False
                if not self.is_expanded and not self.is_animating:
                    self.start_animation(True)
                event.accept()

        def _process_queue(self):
            while not self.log_queue.empty():
                kind, data = self.log_queue.get_nowait()
                if kind == "expand":
                    self.start_animation(data)
                elif kind == "toggle":
                    self.start_animation(not self.is_expanded)
                elif kind == "log":
                    text, tag = data if isinstance(data, tuple) else (str(data), "")
                    self.log_console.append(text)
                    if not self.is_expanded and not self.is_animating:
                        self.start_animation(True)
                elif kind == "status":
                    status, title = data
                    self.current_status = status
                    self.lbl_status.setText(f"● {status}")
                    if status in ["BUSY", "COMPUTING"]:
                        self.lbl_status.setStyleSheet("background: #fdf2f8; color: #db2777; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 3px 8px;")
                        if not self.is_expanded and not self.is_animating:
                            self.start_animation(True)
                    else:
                        self.lbl_status.setStyleSheet("background: #ede9fe; color: #7c3aed; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 3px 8px;")
                        QTimer.singleShot(4000, self._auto_collapse_if_idle)
                    if title:
                        self.task_text = title
                        self.lbl_task.setText(title)
                elif kind == "telemetry":
                    self.gpu_text = data
                    self.lbl_telem.setText(data)

        def _auto_collapse_if_idle(self):
            if self.current_status in ["ONLINE", "READY"] and self.is_expanded and not self.is_animating:
                self.start_animation(False)

    class PyQtOverlayHUD:
        """Controller wrapper for PyQtHUDWidget."""
        def __init__(self, node_id: str = "dgx-node-1", node_name: str = "DGX Spark 01"):
            self.node_id = node_id
            self.node_name = node_name
            self.widget = None
            self.log_queue = queue.Queue()

        def start_hud_thread(self):
            # Handled via run_main_loop on main thread
            pass

        def run_main_loop(self, worker_func):
            """Executes QApplication on the main thread (required by Qt/X11)."""
            try:
                app = QApplication.instance()
                if not app:
                    app = QApplication([sys.argv[0]])
                self.widget = PyQtHUDWidget(node_id=self.node_id, node_name=self.node_name, shared_queue=self.log_queue)
                self.widget.show()

                t = threading.Thread(target=worker_func, daemon=True)
                t.start()

                sys.exit(app.exec_())
            except Exception as e:
                print(f"[!] PyQt HUD exception: {e}")
                # Fallback to worker loop if GUI fails
                worker_func()

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

        def set_expanded(self, expand: bool):
            self.log_queue.put(("expand", expand))

        def toggle_expand(self):
            self.log_queue.put(("toggle", None))

class OverlayHUD:
    """Crash-proof Transparent Glassmorphic HUD with glowing Purple Atom Motif:
    - Floating frosted glass capsule (154x56) in idle state with real-time revolving purple atom.
    - Damped spring-elastic expansion into a spacious glassmorphic console (620x430).
    - 100% pure standard Tkinter: Zero ctypes, zero native C calls, zero segmentation faults.
    - True window translucency (-alpha 0.86) with crisp specular glass borders (#c4b5fd).
    """
    def __init__(self, node_id: str = "dgx-node-1", node_name: str = "DGX Spark 01"):
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()
        self.root = None
        self.is_expanded = False
        self.is_animating = False
        self.current_status = "ONLINE"
        self.pulse_phase = False
        self.atom_phase = 0.0

        # UI Dimensions
        self.mini_w = 154
        self.mini_h = 56
        self.full_w = 620
        self.full_h = 430
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

            # Frosted Glassmorphism Palette (Soft lavender mist / translucent glass)
            glass_bg = "#f8f7ff"         # Frosted lavender glass canvas
            glass_card = "#ffffff"       # Frosted glass card
            glass_border = "#c4b5fd"     # Specular glass border rim
            recessed_tray = "#ffffff"    # Frosted glass trough
            text_primary = "#0f172a"     # Crisp charcoal text
            text_secondary = "#334155"   # Dark slate
            text_muted = "#64748b"       # Soft slate subtext
            accent_purple = "#7c3aed"    # Radiant purple / violet (from Atom motif)
            accent_lavender = "#ede9fe"  # Frosted lavender badge pill

            self.root.configure(bg=glass_bg)
            try:
                self.root.attributes("-alpha", 0.86)
            except Exception:
                pass

            self.screen_width = self.root.winfo_screenwidth()
            pos_x_mini = max(24, self.screen_width - self.mini_w - 24)
            self.root.geometry(f"{self.mini_w}x{self.mini_h}+{pos_x_mini}+{self.pos_y}")

            # Outer Glass Border Container
            self.main_container = tk.Frame(
                self.root,
                bg=glass_bg,
                highlightbackground=glass_border,
                highlightthickness=1.5
            )
            self.main_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

            # ========================================================
            # 1. FLOATING FROSTED GLASS CAPSULE (Idle State)
            # ========================================================
            self.mini_frame = tk.Frame(self.main_container, bg=glass_bg, cursor="hand2")
            self.mini_frame.pack(fill=tk.BOTH, expand=True)

            # Left: Purple Atom Canvas (48x48)
            self.atom_canvas = tk.Canvas(
                self.mini_frame,
                width=48,
                height=48,
                bg=glass_bg,
                highlightthickness=0,
                cursor="hand2"
            )
            self.atom_canvas.pack(side=tk.LEFT, padx=(4, 0), pady=4)

            # Draw static atom orbital tracks (a=17, b=7)
            cx, cy = 24, 24
            a, b = 17, 7
            orbit_colors = ["#8b5cf6", "#9333ea", "#7c3aed"]
            for idx, angle_deg in enumerate(self.orbits):
                rad = math.radians(angle_deg)
                pts = []
                for step in range(36):
                    t = 2 * math.pi * step / 36.0
                    x = cx + a * math.cos(t) * math.cos(rad) - b * math.sin(t) * math.sin(rad)
                    y = cy + a * math.cos(t) * math.sin(rad) + b * math.sin(t) * math.cos(rad)
                    pts.extend([x, y])
                pts.extend([pts[0], pts[1]])
                self.atom_canvas.create_line(pts, fill=orbit_colors[idx], width=1.5, smooth=True)

            # Glowing purple nucleus vortex
            self.atom_canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#ede9fe", outline="")  # Lavender corona
            self.atom_canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#8b5cf6", outline="")  # Purple halo
            self.atom_canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#7c3aed", outline="")  # Violet core
            self.atom_canvas.create_oval(cx - 1, cy - 1, cx + 1, cy + 1, fill="#ffffff", outline="")  # Star center

            # Right: Capsule text and live status pill
            r_frame = tk.Frame(self.mini_frame, bg=glass_bg, cursor="hand2")
            r_frame.pack(side=tk.LEFT, padx=(6, 8), fill=tk.Y, pady=6)

            title_lbl = tk.Label(r_frame, text="AEGIS Spark", fg="#1e1b4b", bg=glass_bg, font=("Helvetica", 9, "bold"), cursor="hand2")
            title_lbl.pack(anchor="w")

            status_pill = tk.Frame(r_frame, bg=accent_lavender, padx=6, pady=1, cursor="hand2")
            status_pill.pack(anchor="w", pady=(2, 0))

            self.mini_dot = tk.Label(status_pill, text="●", fg="#10b981", bg=accent_lavender, font=("Helvetica", 7), cursor="hand2")
            self.mini_dot.pack(side=tk.LEFT)

            self.mini_lbl = tk.Label(status_pill, text=" ONLINE", fg=accent_purple, bg=accent_lavender, font=("Helvetica", 7, "bold"), cursor="hand2")
            self.mini_lbl.pack(side=tk.LEFT)

            # Bind clicks to spring-expand
            self.mini_frame.bind("<Button-1>", lambda e: self.start_animation(True))
            self.atom_canvas.bind("<Button-1>", lambda e: self.start_animation(True))
            title_lbl.bind("<Button-1>", lambda e: self.start_animation(True))
            status_pill.bind("<Button-1>", lambda e: self.start_animation(True))
            self.mini_dot.bind("<Button-1>", lambda e: self.start_animation(True))
            self.mini_lbl.bind("<Button-1>", lambda e: self.start_animation(True))

            # Initial draw of revolving electrons
            self._update_atom_electrons()

            # ========================================================
            # 2. BIGGER TRANSPARENT GLASS CONSOLE (Expanded State)
            # ========================================================
            self.full_frame = tk.Frame(self.main_container, bg=glass_bg)

            # Frosted Glass Header (Height 44px)
            hdr = tk.Frame(self.full_frame, bg=glass_card, height=44)
            hdr.pack(fill=tk.X, padx=0, pady=0)

            atom_icon = tk.Label(hdr, text="⚛", fg=accent_purple, bg=glass_card, font=("Helvetica", 16, "bold"))
            atom_icon.pack(side=tk.LEFT, padx=(12, 6))

            title_full_lbl = tk.Label(hdr, text=f"AEGIS Studio  •  {self.node_name}", fg=text_primary, bg=glass_card, font=("Helvetica", 11, "bold"))
            title_full_lbl.pack(side=tk.LEFT)

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
            body = tk.Frame(self.full_frame, bg=glass_bg)
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
                bg=glass_bg,
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
                wrap="word",
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

            # Enable window dragging on both mini capsule and expanded header
            self._bind_drag(self.mini_frame)
            self._bind_drag(self.atom_canvas)
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
        self.atom_canvas.delete("atom_electron")
        cx, cy = 24, 24
        a, b = 17, 7
        for idx, angle_deg in enumerate(self.orbits):
            rad = math.radians(angle_deg)
            t_el = self.atom_phase + idx * (2 * math.pi / 3.0)
            x_el = cx + a * math.cos(t_el) * math.cos(rad) - b * math.sin(t_el) * math.sin(rad)
            y_el = cy + a * math.cos(t_el) * math.sin(rad) + b * math.sin(t_el) * math.cos(rad)
            # Electron lilac glow aura
            self.atom_canvas.create_oval(
                x_el - 3.5, y_el - 3.5, x_el + 3.5, y_el + 3.5,
                fill="#c084fc", outline="", tags="atom_electron"
            )
            # Electron brilliant white core
            self.atom_canvas.create_oval(
                x_el - 1.8, y_el - 1.8, x_el + 1.8, y_el + 1.8,
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
        """Tactile gentle pulse on the status pip."""
        if not self.root:
            return
        if not self.is_expanded and not self.is_animating:
            self.pulse_phase = not self.pulse_phase
            base_col = "#10b981" if self.current_status in ["ONLINE", "READY"] else "#7c3aed"
            dim_col = "#059669" if self.current_status in ["ONLINE", "READY"] else "#5b21b6"
            cur = base_col if self.pulse_phase else dim_col
            self.mini_dot.configure(fg=cur)
        self.root.after(1200, self._pulse_loop)

    def toggle_expand(self):
        self.start_animation(not self.is_expanded)

    def set_expanded(self, expand: bool):
        self.log_queue.put(("expand", expand))

    def start_animation(self, target_expanded: bool):
        """Spring-elastic expansion / minimization between glass capsule and console."""
        if self.is_animating or self.is_expanded == target_expanded:
            return

        self.is_animating = True
        self.target_expanded = target_expanded

        if target_expanded:
            self.mini_frame.pack_forget()
            self.full_frame.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.mini_w, self.mini_h
            end_w, end_h = self.full_w, self.full_h
        else:
            self.full_frame.pack_forget()
            self.mini_frame.pack(fill=tk.BOTH, expand=True)
            start_w, start_h = self.full_w, self.full_h
            end_w, end_h = self.mini_w, self.mini_h

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
        pos_x = max(24, self.screen_width - w - 24)

        self.root.geometry(f"{w}x{h}+{pos_x}+{self.pos_y}")

        if step < total_steps:
            self.root.after(14, self._step_animation, step + 1, total_steps, start_w, end_w, start_h, end_h)
        else:
            self.is_expanded = self.target_expanded
            self.is_animating = False
            border = "#7c3aed" if self.current_status == "BUSY" else ("#10b981" if self.current_status in ["ONLINE", "READY"] else "#c4b5fd")
            self.main_container.configure(highlightbackground=border)

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

                    # Update Mini Capsule labels
                    self.mini_dot.configure(fg=color)
                    self.mini_lbl.configure(text=f" {self.current_status}", fg=color)

                    # Dynamic animation: Enlarge on BUSY, auto-minimise to capsule after idle
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
                    self.mini_dot.configure(fg="#ef4444")
                    self.mini_lbl.configure(text=" ALERT", fg="#ef4444")
                    self.log_text.insert(tk.END, f"\n⚠️ [GATEWAY ALERT] {data}\n", "red")
                    self.log_text.see(tk.END)
                    self.start_animation(True)
                elif kind == "locked":
                    locked, reason = data
                    if locked:
                        self.status_lbl.configure(text="LOCKED", fg="#dc2626")
                        self.status_dot.configure(fg="#dc2626")
                        self.mini_dot.configure(fg="#dc2626")
                        self.mini_lbl.configure(text=" LOCKED", fg="#dc2626")
                        self.task_lbl.configure(text=f"NODE LOCKED: {reason or 'Administrative Lock'}")
                        self.log_text.insert(tk.END, f"\n🔒 [STATION LOCKED] {reason}\n", "red")
                        self.start_animation(True)
                    else:
                        self.status_lbl.configure(text="ONLINE", fg="#10b981")
                        self.status_dot.configure(fg="#10b981")
                        self.mini_dot.configure(fg="#10b981")
                        self.mini_lbl.configure(text=" ONLINE", fg="#10b981")
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
                 default_model: str = "qwen2.5-coder:32b",
                 default_num_ctx: int = 65536,
                 poll_interval: float = 6.0,
                 show_hud: bool = True):
        self.node_id = node_id
        self.gateway_url = gateway_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.storage_url = storage_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.default_model = os.environ.get("AEGIS_MODEL", default_model)
        self.default_num_ctx = int(os.environ.get("AEGIS_NUM_CTX", default_num_ctx))
        self.poll_interval = poll_interval
        self.show_hud = show_hud

        self.current_task_id = None
        self.is_running = True
        self.is_locked = False
        os.makedirs("./workspace", exist_ok=True)

        self.hud = None
        if self.show_hud:
            try:
                if "DISPLAY" not in os.environ and sys.platform != "win32":
                    for disp in [":0", ":1"]:
                        if os.path.exists(f"/tmp/.X11-unix/X{disp.replace(':', '')}"):
                            os.environ["DISPLAY"] = disp
                            break
                    if "DISPLAY" not in os.environ:
                        os.environ["DISPLAY"] = ":0"

                if HAS_PYQT:
                    self.hud = PyQtOverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                    print(f"[✓] PyQt5 Translucent Animated Orb HUD ready on DISPLAY {os.environ.get('DISPLAY', ':0')}")
                elif HAS_TK:
                    self.hud = OverlayHUD(node_id=self.node_id, node_name=f"DGX Spark {self.node_id}")
                    self.hud.start_hud_thread()
                    print(f"[✓] Tkinter Glass HUD activated on DISPLAY {os.environ.get('DISPLAY', ':0')}")
                else:
                    print("[!] No GUI library available for HUD. Run 'sudo apt-get install python3-pyqt5' or 'pip install PyQt5'.")
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

    def execute_ollama_query(self, prompt: str, model_name: str = None, num_ctx: int = None) -> str:
        """Queries local Ollama instance with high context window (up to 128K) and live HUD streaming."""
        chosen_model = model_name or self.default_model
        ctx = num_ctx or self.default_num_ctx

        print(f"\n[{self.node_id}] Querying model: {chosen_model} (Context Window: {ctx:,} tokens)...")
        if self.hud:
            self.hud.append_log(f"[{self.node_id}] Model: {chosen_model} | Context: {ctx:,} tokens | GPU: Active\n", "purple")

        system_instruction = (
            "You are an expert autonomous software engineer executing tasks on an NVIDIA DGX node with 128GB Unified Memory.\n"
            "Generate complete, robust, production-quality code to fulfill the user's request.\n"
            "When creating multiple files, output EACH file in its own markdown code block (```language ... ```).\n"
            "On the very first line inside EACH code block, specify the exact filename as a comment:\n"
            "- For Python: # filename: filename.py\n"
            "- For JavaScript/TypeScript/C++/C: // filename: filename.js\n"
            "- For HTML/CSS/SQL: /* filename: style.css */ or <!-- filename: index.html -->\n"
            "Always output full, complete code without placeholders or ellipses ('// ...').\n"
            "Do NOT include file upload code, network synchronization, or destination URLs; the autonomous runtime environment automatically captures and synchronizes all generated artifacts."
        )

        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": True,
            "options": {
                "num_ctx": ctx,            # 65,536 tokens by default!
                "num_predict": 16384,      # Large generation output
                "temperature": 0.2
            }
        }

        full_chunks = []
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=600.0) as resp:
                token_counter = 0
                for line in resp:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("response", "")
                        if token:
                            full_chunks.append(token)
                            token_counter += 1
                            if self.hud and token_counter % 6 == 0:
                                self.hud.append_log(token)
                        if chunk.get("done", False):
                            break
                    except Exception:
                        continue
            resp_text = "".join(full_chunks)
        except Exception as e:
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str:
                print(f"[*] Model '{chosen_model}' not found in Ollama. Auto-pulling on GPU...")
                if self.hud:
                    self.hud.append_log(f"[*] Auto-pulling {chosen_model} on local GPU...\n", "amber")
                subprocess.run(["ollama", "pull", chosen_model])
                payload["stream"] = False
                res = http_post_json(url, payload, timeout=600.0)
                resp_text = res.get("response", "")
            else:
                payload["stream"] = False
                res = http_post_json(url, payload, timeout=600.0)
                resp_text = res.get("response", "")

        if self.hud and resp_text and not full_chunks:
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
                code_lines = code.splitlines()[:4]
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

        # Generate manifest.json indexing all extracted files
        manifest = {
            "task_id": task_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "total_files": len(saved_files),
            "files": [
                {
                    "filename": f[0],
                    "size_bytes": os.path.getsize(f[1]) if os.path.exists(f[1]) else 0,
                    "vault_status": f[2]
                }
                for f in saved_files
            ]
        }
        manifest_path = os.path.join(task_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        self.upload_to_i7_vault(manifest_path, task_id)
        saved_files.append(("manifest.json", manifest_path, "manifest_created"))

        return saved_files

    def execute_task(self, task: dict):
        if self.is_locked:
            print(f"[{self.node_id}] Task rejected: Node is LOCKED.")
            return

        task_id = task.get("task_id", f"tsk_{int(time.time())}")
        prompt = task.get("prompt", "")
        model_name = task.get("model") or self.default_model
        num_ctx = int(task.get("num_ctx") or self.default_num_ctx)
        self.current_task_id = task_id

        print("\n" + "=" * 65)
        print(f"[{self.node_id}] REVERSE HEARTBEAT TASK RECEIVED: {task_id}")
        print(f"Prompt: {prompt}")
        print(f"Model: {model_name} | Context: {num_ctx:,} tokens")
        print("=" * 65)

        if self.hud:
            self.hud.update_status("BUSY", task_title=prompt)
            self.hud.append_log(f"\n>>> [TASK {task_id}] Model: {model_name} (Ctx: {num_ctx:,})\nPrompt: {prompt}\n", "purple")

        # 1. Run inference on local GPU with high context window
        stdout_log = self.execute_ollama_query(prompt, model_name=model_name, num_ctx=num_ctx)

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
            self.hud.append_log(f"\n[✓ Task {task_id} Complete - Auto-minimizing to orb in 4s...]\n", "green")
            threading.Timer(4.0, lambda: self.hud.set_expanded(False)).start()
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

    def start(self):
        self.start_polling()

    def start_polling(self):
        """Starts agent. If PyQt HUD is active, runs Qt on main thread and polling in a worker thread."""
        if self.hud and hasattr(self.hud, "run_main_loop"):
            self.hud.run_main_loop(self._polling_loop)
        else:
            self._polling_loop()

    def _polling_loop(self):
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
    parser.add_argument("--model", default=os.environ.get("AEGIS_MODEL", "qwen2.5-coder:32b"), help="Local Ollama model name (e.g. qwen2.5-coder:32b, llama3.3:70b)")
    parser.add_argument("--ctx", type=int, default=int(os.environ.get("AEGIS_NUM_CTX", "65536")), help="Context window token limit (default: 65536, up to 131072)")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds")
    parser.add_argument("--no-hud", action="store_true", help="Disable desktop screen overlay HUD")
    args = parser.parse_args()

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
        print("\nAgent stopped.")
