#!/usr/bin/env python3
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
    from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QRectF, pyqtSignal, QObject, QEvent
    from PyQt5.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, 
        QLinearGradient, QPainterPath, QCursor, QFontMetrics, QRegion
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


# ── Dynamic Curated Pastel Palettes per Node ──────────────────────────────
NODE_PASTEL_THEMES = {
    "dgx-node-1": {
        "name": "DGX Spark 01 • Lead Coder",
        "primary": QColor(167, 139, 250),     # Soft Pastel Lavender (#A78BFA)
        "secondary": QColor(196, 181, 253),   # Pale Lavender (#C4B5FD)
        "dim": QColor(167, 139, 250, 40),
        "border": QColor(167, 139, 250, 95),
        "glow": QColor(167, 139, 250, 60),
        "hex": "#A78BFA",
        "hex_dim": "rgba(167, 139, 250, 0.15)",
        "tag": "Lavender"
    },
    "dgx-node-2": {
        "name": "DGX Spark 02 • Reviewer & QA",
        "primary": QColor(125, 211, 252),     # Soft Pastel Sky Blue (#7DD3FC)
        "secondary": QColor(186, 230, 253),   # Pale Sky (#BAE6FD)
        "dim": QColor(125, 211, 252, 40),
        "border": QColor(125, 211, 252, 95),
        "glow": QColor(125, 211, 252, 60),
        "hex": "#7DD3FC",
        "hex_dim": "rgba(125, 211, 252, 0.15)",
        "tag": "Sky"
    },
    "dgx-node-3": {
        "name": "DGX Spark 03 • Multimodal Vision",
        "primary": QColor(110, 231, 183),     # Soft Pastel Mint (#6EE7B7)
        "secondary": QColor(167, 243, 208),   # Pale Mint (#A7F3D0)
        "dim": QColor(110, 231, 183, 40),
        "border": QColor(110, 231, 183, 95),
        "glow": QColor(110, 231, 183, 60),
        "hex": "#6EE7B7",
        "hex_dim": "rgba(110, 231, 183, 0.15)",
        "tag": "Mint"
    },
    "dgx-node-4": {
        "name": "DGX Spark 04 • Deep Reasoner",
        "primary": QColor(253, 164, 175),     # Soft Pastel Rose (#FDA4AF)
        "secondary": QColor(254, 205, 211),   # Pale Rose (#FECDD3)
        "dim": QColor(253, 164, 175, 40),
        "border": QColor(253, 164, 175, 95),
        "glow": QColor(253, 164, 175, 60),
        "hex": "#FDA4AF",
        "hex_dim": "rgba(253, 164, 175, 0.15)",
        "tag": "Rose"
    },
    "dgx-node-5": {
        "name": "DGX Spark 05 • Security Auditor",
        "primary": QColor(252, 211, 77),      # Soft Pastel Amber (#FCD34D)
        "secondary": QColor(254, 240, 138),   # Pale Amber (#FEF08A)
        "dim": QColor(252, 211, 77, 40),
        "border": QColor(252, 211, 77, 95),
        "glow": QColor(252, 211, 77, 60),
        "hex": "#FCD34D",
        "hex_dim": "rgba(252, 211, 77, 0.15)",
        "tag": "Amber"
    },
    "dgx-node-6": {
        "name": "DGX Spark 06 • Visual Studio",
        "primary": QColor(253, 186, 116),     # Soft Pastel Peach (#FDBA74)
        "secondary": QColor(254, 215, 170),   # Pale Peach (#FED7AA)
        "dim": QColor(253, 186, 116, 40),
        "border": QColor(253, 186, 116, 95),
        "glow": QColor(253, 186, 116, 60),
        "hex": "#FDBA74",
        "hex_dim": "rgba(253, 186, 116, 0.15)",
        "tag": "Peach"
    },
    "dgx-node-7": {
        "name": "DGX Spark 07 • Tool & Git Agent",
        "primary": QColor(129, 140, 248),     # Soft Pastel Periwinkle (#818CF8)
        "secondary": QColor(199, 210, 254),   # Pale Periwinkle (#C7D2FE)
        "dim": QColor(129, 140, 248, 40),
        "border": QColor(129, 140, 248, 95),
        "glow": QColor(129, 140, 248, 60),
        "hex": "#818CF8",
        "hex_dim": "rgba(129, 140, 248, 0.15)",
        "tag": "Periwinkle"
    },
    "dgx-node-8": {
        "name": "DGX Spark 08 • Doc Synthesizer",
        "primary": QColor(94, 234, 212),      # Soft Pastel Teal (#5EEAD4)
        "secondary": QColor(153, 246, 228),   # Pale Teal (#99F6E4)
        "dim": QColor(94, 234, 212, 40),
        "border": QColor(94, 234, 212, 95),
        "glow": QColor(94, 234, 212, 60),
        "hex": "#5EEAD4",
        "hex_dim": "rgba(94, 234, 212, 0.15)",
        "tag": "Teal"
    }
}

def get_node_theme(node_id: str):
    norm_id = node_id.lower().strip()
    return NODE_PASTEL_THEMES.get(norm_id, NODE_PASTEL_THEMES["dgx-node-1"])

# Global Neutral Minimal Palette
COLOR_BG_DARK = QColor(11, 14, 20, 242)          # Deep Frosted Apple Glass
COLOR_CARD_DARK = QColor(18, 22, 31, 235)        # Card Glass
COLOR_TEXT_WHITE = QColor(248, 250, 252, 255)    # Clean Soft White
COLOR_TEXT_MUTED = QColor(148, 163, 184, 230)    # Soft Slate Dim
COLOR_BORDER_SUBTLE = QColor(255, 255, 255, 20)  # Apple Ultra-Thin Specular Border


def ease_in_out(t: float) -> float:
    """Smooth Apple/Perlin C2-continuous Ease-In Ease-Out animation curve.
    Starts with gentle acceleration (ease-in), glides fast through the middle,
    and gently decelerates to a soft stop (ease-out) with zero sudden jumps.
    """
    clamped = max(0.0, min(1.0, float(t)))
    # Smootherstep polynomial: 6t^5 - 15t^4 + 10t^3
    return clamped * clamped * clamped * (clamped * (6.0 * clamped - 15.0) + 10.0)


if sys.platform != "win32":
    for _ev in ["WINDOWID", "GNOME_TERMINAL_SCREEN", "GNOME_TERMINAL_SERVICE"]:
        if _ev in os.environ:
            del os.environ[_ev]


def make_pure_desktop_overlay(widget):
    """Ensures widget behaves as a pure desktop overlay, 100% invisible to taskbars, docks, and Alt-Tab."""
    if sys.platform != "win32":
        try:
            win_id = int(widget.winId())
            # Break any transient bond to gnome-terminal so it is anchored strictly to the root desktop
            subprocess.run([
                "xprop", "-id", str(win_id),
                "-remove", "WM_TRANSIENT_FOR"
            ], capture_output=True, timeout=0.3)
            # Space-separated EWMH atoms (xprop atom format does NOT use commas)
            subprocess.run([
                "xprop", "-id", str(win_id),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_SKIP_TASKBAR _NET_WM_STATE_SKIP_PAGER _NET_WM_STATE_ABOVE"
            ], capture_output=True, timeout=0.3)
            # Enable Picom/KWin/Mutter blur behind translucent window
            subprocess.run([
                "xprop", "-id", str(win_id),
                "-f", "_KDE_NET_WM_BLUR_BEHIND_REGION", "32c",
                "-set", "_KDE_NET_WM_BLUR_BEHIND_REGION", "0"
            ], capture_output=True, timeout=0.3)
        except Exception:
            pass


class CornerLogoOrb(QWidget):
    """Floating Minimal Glass Orb anchored in the bottom-right corner.
    - Soft breathing pastel aura matching node identity.
    - Clean geometric core with delicate orbital ring.
    - Clicking toggles the central Apple-style Dynamic Island.
    """
    clicked = pyqtSignal()

    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.theme = get_node_theme(self.node_id)
        self.orb_size = 64
        self.atom_phase = 0.0
        self.pulse_phase = 0.0
        self.is_busy = False
        self.is_hovered = False

        # Pure desktop overlay: Qt.ToolTip unconditionally enables override-redirect in X11
        # Bypasses Mutter window placement and completely eliminates GNOME dock presence
        flags = Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "BypassWindowManagerHint"):
            flags |= Qt.BypassWindowManagerHint
        if sys.platform != "win32" and hasattr(Qt, "X11BypassWindowManagerHint"):
            flags |= Qt.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setWindowTitle("")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus, True)
        self.setMouseTracking(True)
        self.setFixedSize(self.orb_size, self.orb_size)

        self._position_in_corner()

        # Dragging support
        self._drag_active = False
        self._drag_pos = QPoint()
        self._moved = False

        # Animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(28)

    def update_node(self, node_id: str):
        self.node_id = node_id
        self.theme = get_node_theme(node_id)
        self.update()

    def _position_in_corner(self):
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
        else:
            avail = QRect(0, 0, 1920, 1080)
        margin_x = 24
        margin_y = 24
        pos_x = int(avail.x() + avail.width() - self.orb_size - margin_x)
        pos_y = int(avail.y() + avail.height() - self.orb_size - margin_y)
        self.setGeometry(pos_x, pos_y, self.orb_size, self.orb_size)

    def play_entrance_animation(self):
        self._position_in_corner()
        self.pulse_phase = 0.0
        self.update()

    def _tick(self):
        speed = 0.07 if self.is_busy else 0.03
        self.atom_phase = (self.atom_phase + speed) % (2 * math.pi)
        self.pulse_phase = (self.pulse_phase + 0.05) % (2 * math.pi)
        self.update()

    def set_busy(self, busy: bool):
        self.is_busy = busy
        self.update()

    def enterEvent(self, event):
        self.is_hovered = True
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_active and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPos() - self._drag_pos
            self.move(new_pos)
            self._moved = True
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = False
            if not self._moved:
                self.clicked.emit()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        r = (self.orb_size - 12) / 2.0

        p_col = self.theme["primary"]

        # 1. Subtle Outer Breathing Halo (Soft Pastel Glow)
        pulse_alpha = int(25 + 18 * math.sin(self.pulse_phase))
        if self.is_hovered:
            pulse_alpha = min(75, pulse_alpha + 25)
        halo_grad = QRadialGradient(cx, cy, r * 1.35)
        halo_grad.setColorAt(0.0, QColor(p_col.red(), p_col.green(), p_col.blue(), pulse_alpha))
        halo_grad.setColorAt(0.7, QColor(p_col.red(), p_col.green(), p_col.blue(), int(pulse_alpha * 0.3)))
        halo_grad.setColorAt(1.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo_grad))
        painter.drawEllipse(QRectF(cx - r * 1.3, cy - r * 1.3, r * 2.6, r * 2.6))

        # 2. Sleek Translucent Glass Body
        body_grad = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.2)
        body_grad.setColorAt(0.0, QColor(32, 40, 58, 195))
        body_grad.setColorAt(0.65, QColor(18, 24, 36, 185))
        body_grad.setColorAt(1.0, QColor(10, 14, 24, 210))
        painter.setBrush(QBrush(body_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 3. Soft Pastel Edge Rim
        rim_alpha = 180 if (self.is_busy or self.is_hovered) else 80
        rim_color = QColor(p_col.red(), p_col.green(), p_col.blue(), rim_alpha)
        painter.setPen(QPen(rim_color, 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 4. Minimal Dual Rotating Orbital Rings (Pastel)
        orbits = [-28.0, 62.0]
        a = r * 0.65
        b = r * 0.22

        for idx, angle_deg in enumerate(orbits):
            rad = math.radians(angle_deg)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            path = QPainterPath()
            steps = 32
            for s in range(steps + 1):
                t = 2 * math.pi * s / float(steps)
                x = cx + a * math.cos(t) * cos_a - b * math.sin(t) * sin_a
                y = cy + a * math.cos(t) * sin_a + b * math.sin(t) * cos_a
                if s == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            ring_col = QColor(p_col.red(), p_col.green(), p_col.blue(), 130 if idx == 0 else 90)
            painter.setPen(QPen(ring_col, 1.1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

            # Smooth orbital particle
            e_t = self.atom_phase + (idx * math.pi)
            ex = cx + a * math.cos(e_t) * cos_a - b * math.sin(e_t) * sin_a
            ey = cy + a * math.cos(e_t) * sin_a + b * math.sin(e_t) * cos_a

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(p_col))
            painter.drawEllipse(QRectF(ex - 2.2, ey - 2.2, 4.4, 4.4))

        # 5. Glowing Center Nucleus
        nuc_grad = QRadialGradient(cx, cy, 6.0)
        nuc_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        nuc_grad.setColorAt(0.5, p_col)
        nuc_grad.setColorAt(1.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(nuc_grad))
        painter.drawEllipse(QRectF(cx - 5.5, cy - 5.5, 11.0, 11.0))

        # 6. Subtle Status Pip
        pip_col = QColor(251, 113, 133) if self.is_busy else p_col
        pip_y = cy + r - 3.0
        painter.setBrush(QBrush(pip_col))
        painter.drawEllipse(QRectF(cx - 2.5, pip_y, 5.0, 5.0))


class Spring:
    """Second-order harmonic spring physics engine: m*x'' + c*x' + k*(x - target) = 0.
    Provides organic tactile overshoot, mass inertia, and natural rubbery snap
    mirroring the Apple iOS Dynamic Island fluid transitions.
    """
    def __init__(self, val: float = 0.0, target: float = 0.0, stiffness: float = 305.0, damping: float = 21.5, mass: float = 1.0):
        self.val = float(val)
        self.target = float(target)
        self.vel = 0.0
        self.k = float(stiffness)  # Spring constant
        self.c = float(damping)    # Viscous damping coefficient
        self.m = float(mass)       # Mass

    def snap_to(self, val: float):
        """Immediately reset position and cancel velocity."""
        self.val = float(val)
        self.target = float(val)
        self.vel = 0.0

    def set_target(self, target: float):
        self.target = float(target)

    def update(self, dt: float = 0.016) -> bool:
        """Advance physics state by dt using semi-implicit Euler integration.
        Returns True if spring has settled at equilibrium, False otherwise.
        """
        displacement = self.val - self.target
        force = -self.k * displacement - self.c * self.vel
        accel = force / self.m

        # Semi-implicit Euler integration
        self.vel += accel * dt
        self.val += self.vel * dt

        # Settle condition: sub-pixel threshold
        if abs(displacement) < 0.25 and abs(self.vel) < 0.35:
            self.val = self.target
            self.vel = 0.0
            return True
        return False


class DynamicIslandWidget(QWidget):
    """Central Apple-Style Dynamic Island Notch with Harmonic Spring Physics Engine.
    Architecture:
    - Fixed Oversized Transparent Viewport (760 x 500 px) anchored at top-center.
      Never resizes on animation ticks, eliminating OS/X11 window resizing jitter and flicker.
    - Second-order harmonic spring physics (F = -kx - cv) with organic overshoot & rubbery bounce.
    - Input masking via QRegion so transparent areas outside the active capsule are 100% click-through.
    - True compositor glassmorphism with specular rim highlight, ambient soft aura, and optical border.

    States:
    1. STATE_PILL_IDLE:  Compact ~240 x 36 px minimal resting capsule at top-center.
    2. STATE_PILL_BUSY:  Horizontally stretched ~540 x 36 px (SAME 36px HEIGHT!) with live activity & wave.
    3. STATE_ALERT_DONE: Downward stretched ~440 x 108 px notification card with checkmark & file details.
    4. STATE_EXPANDED:   Full ~680 x 440 px elegant frosted developer hub & telemetry console.
    """
    minimize_to_corner = pyqtSignal()
    node_switched = pyqtSignal(str)
    model_changed = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    STATE_PILL_IDLE = 0
    STATE_PILL_BUSY = 1
    STATE_ALERT_DONE = 2
    STATE_EXPANDED = 3

    VIEWPORT_W = 760
    VIEWPORT_H = 500

    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", shared_queue=None, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.theme = get_node_theme(self.node_id)
        self.log_queue = shared_queue or queue.Queue()

        self.state = self.STATE_PILL_IDLE
        self.target_state = self.STATE_PILL_IDLE
        self.current_status = "ONLINE"
        self.active_model = "qwen2.5-coder:32b"
        self.task_text = "Ready • Standing by"
        self.gpu_text = "GPU 0%"
        self.is_busy = False

        # Authentic Apple Dynamic Island State Dimensions
        self.dim_pill_idle = (260, 36)
        self.dim_pill_busy = (540, 36)    # EXACT SAME 36px HEIGHT!
        self.dim_alert_done = (440, 108)  # Downward stretch droplet card
        self.dim_expanded = (680, 440)    # Full developer console

        # Harmonic Spring Physics Engine (Stiffness, Damping, Mass)
        # Provides organic tactile overshoot and rubbery bounce
        self.spring_w = Spring(val=self.dim_pill_idle[0], target=self.dim_pill_idle[0], stiffness=305.0, damping=21.5, mass=1.0)
        self.spring_h = Spring(val=self.dim_pill_idle[1], target=self.dim_pill_idle[1], stiffness=315.0, damping=22.5, mass=1.0)
        self.is_animating = False

        # Fluid desktop dragging support
        self._drag_active = False
        self._drag_start_pos = QPoint()
        self._window_start_pos = QPoint()
        self._moved = False

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._physics_tick)

        # Window Flags: Pure desktop overlay immune to dock and taskbar
        flags = Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "BypassWindowManagerHint"):
            flags |= Qt.BypassWindowManagerHint
        if sys.platform != "win32" and hasattr(Qt, "X11BypassWindowManagerHint"):
            flags |= Qt.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setWindowTitle("")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus, True)
        self.setMouseTracking(True)
        self.target_screen = QApplication.primaryScreen()

        # Fixed viewport: Geometry is set ONCE, never resized on animation ticks!
        self.setFixedSize(self.VIEWPORT_W, self.VIEWPORT_H)

        # Subtle wave & spinner timers
        self.spinner_phase = 0.0
        self.wave_phase = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse_tick)
        self.pulse_timer.start(25)

        # Worker queue processing
        self.q_timer = QTimer(self)
        self.q_timer.timeout.connect(self._process_queue)
        self.q_timer.start(30)

        self._init_ui()
        self._position_viewport()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_viewport()
        self._enable_x11_blur()

    def _enable_x11_blur(self):
        """Instructs X11 compositors (Picom / KWin / Mutter) to blur desktop under the notch."""
        if sys.platform != "win32":
            try:
                wid = int(self.winId())
                subprocess.run(
                    ["xprop", "-id", str(wid), "-f", "_KDE_NET_WM_BLUR_BEHIND_REGION", "32c", "-set", "_KDE_NET_WM_BLUR_BEHIND_REGION", "0"],
                    capture_output=True, timeout=0.3
                )
            except Exception:
                pass

    def _position_viewport(self):
        """Positions the fixed viewport at top-center of the active screen once."""
        screen = getattr(self, "target_screen", None) or QApplication.primaryScreen()
        if not screen:
            screen = QApplication.screenAt(QCursor.pos())
        if screen:
            geom = screen.geometry()
            avail = screen.availableGeometry()
        else:
            geom = QRect(0, 0, 1920, 1080)
            avail = geom
        pos_x = int(geom.x() + (geom.width() - self.VIEWPORT_W) / 2)
        top_offset = avail.y() + 4 if avail.y() > geom.y() else (geom.y() + 8)
        pos_y = int(top_offset)
        self.setGeometry(pos_x, pos_y, self.VIEWPORT_W, self.VIEWPORT_H)
        self._sync_capsule_geometry()

    def _reposition_center(self):
        """Preserved for API compatibility."""
        self._position_viewport()

    def _sync_capsule_geometry(self):
        """Syncs the internal capsule widget and input mask with current spring coordinates."""
        cur_w = max(60.0, self.spring_w.val)
        cur_h = max(28.0, self.spring_h.val)
        capsule_x = (self.VIEWPORT_W - cur_w) / 2.0
        capsule_y = 6.0
        if hasattr(self, "capsule"):
            self.capsule.setGeometry(int(capsule_x), int(capsule_y), int(cur_w), int(cur_h))

        # Shape input mask so all transparent areas outside capsule pass clicks directly to desktop
        pad = 8
        mask_rect = QRect(int(capsule_x - pad), int(capsule_y - pad), int(cur_w + pad * 2), int(cur_h + pad * 2))
        self.setMask(QRegion(mask_rect))

    def play_entrance_animation(self):
        """Harmonic entrance animation: stretches naturally from narrow notch into idle pill."""
        self._position_viewport()
        self.spring_w.snap_to(70.0)
        self.spring_h.snap_to(36.0)
        self.spring_w.set_target(self.dim_pill_idle[0])
        self.spring_h.set_target(self.dim_pill_idle[1])
        self.target_state = self.STATE_PILL_IDLE
        self.is_animating = True
        self.physics_timer.start(16)

    def _init_ui(self):
        # Master Capsule Container
        self.capsule = QWidget(self)
        self.capsule.setObjectName("islandCapsule")
        self.capsule.setStyleSheet("#islandCapsule { background: transparent; }")
        self.capsule.setAttribute(Qt.WA_TranslucentBackground, True)
        self.capsule.installEventFilter(self)

        self.capsule_layout = QVBoxLayout(self.capsule)
        self.capsule_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.capsule_layout.setContentsMargins(8, 4, 8, 4)
        self.capsule_layout.setSpacing(0)

        # ── 1. COMPACT IDLE & HORIZONTALLY STRETCHED BUSY CAPSULE (Height 28px inside 36px) ──
        self.pill_bar = QWidget(self.capsule)
        self.pill_bar.setFixedHeight(28)
        self.pill_bar.installEventFilter(self)
        self.pill_layout = QHBoxLayout(self.pill_bar)
        self.pill_layout.setContentsMargins(4, 0, 4, 0)
        self.pill_layout.setSpacing(6)

        # Symmetrical Spacers to center elements perfectly in Idle state
        self.spacer_left = QtWidgets.QSpacerItem(10, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.pill_layout.addItem(self.spacer_left)

        # Left: Soft Pastel Indicator Dot / Spinner / Checkmark
        self.lbl_dot = QLabel("●", self.pill_bar)
        self.lbl_dot.setAlignment(Qt.AlignCenter)
        self.lbl_dot.installEventFilter(self)
        self.pill_layout.addWidget(self.lbl_dot)

        # Center Identity Badge (SPARK 01 • CODER)
        self.lbl_badge = QLabel(self.pill_bar)
        self.lbl_badge.setAlignment(Qt.AlignCenter)
        self.lbl_badge.installEventFilter(self)
        self.pill_layout.addWidget(self.lbl_badge)

        # Activity summary label (Hidden in Idle, visible when horizontally stretched)
        self.lbl_activity = QLabel(self.task_text, self.pill_bar)
        self.lbl_activity.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.lbl_activity.setVisible(False)
        self.lbl_activity.installEventFilter(self)
        self.pill_layout.addWidget(self.lbl_activity, stretch=2)

        # Model Pill Badge (e.g. 32B, visible when stretched)
        self.lbl_model_pill = QLabel("32B", self.pill_bar)
        self.lbl_model_pill.setAlignment(Qt.AlignCenter)
        self.lbl_model_pill.setVisible(False)
        self.pill_layout.addWidget(self.lbl_model_pill)

        # Telemetry info (Hidden in Idle, visible when stretched)
        self.lbl_telem = QLabel(self.gpu_text, self.pill_bar)
        self.lbl_telem.setAlignment(Qt.AlignCenter)
        self.lbl_telem.setVisible(False)
        self.pill_layout.addWidget(self.lbl_telem)

        # Soft Expand Arrow / Toggle
        self.btn_toggle = QPushButton("▾", self.pill_bar)
        self.btn_toggle.setFixedSize(18, 18)
        self.btn_toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_toggle.clicked.connect(self._toggle_expanded)
        self.pill_layout.addWidget(self.btn_toggle)

        # Right Symmetrical Spacer for Idle Mode Centering
        self.spacer_right = QtWidgets.QSpacerItem(10, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.pill_layout.addItem(self.spacer_right)

        self.capsule_layout.addWidget(self.pill_bar)

        # ── 2. TASK DONE NOTIFICATION DROPLET CARD (Drops Down, Perfectly Centered) ──
        self.done_card = QWidget(self.capsule)
        self.done_card.setVisible(False)
        self.done_card.installEventFilter(self)
        done_layout = QVBoxLayout(self.done_card)
        done_layout.setContentsMargins(10, 6, 10, 6)
        done_layout.setSpacing(4)
        done_layout.setAlignment(Qt.AlignCenter)

        # Row 1: Checkmark + "TASK COMPLETED • SYNCED TO VAULT" (Centered)
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        row1.addStretch(1)

        self.lbl_done_tick = QLabel("✓", self.done_card)
        self.lbl_done_tick.setStyleSheet("color: #34D399; font-size: 13px; font-weight: 900;")
        self.lbl_done_tick.setAlignment(Qt.AlignCenter)
        row1.addWidget(self.lbl_done_tick)

        self.lbl_done_header = QLabel("TASK COMPLETED • SYNCED TO VAULT", self.done_card)
        self.lbl_done_header.setStyleSheet(
            "color: #F8FAFC; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; "
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif;"
        )
        self.lbl_done_header.setAlignment(Qt.AlignCenter)
        row1.addWidget(self.lbl_done_header)
        row1.addStretch(1)
        done_layout.addLayout(row1)

        # Row 2: File Icon + Details (Centered)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        row2.addStretch(1)

        self.lbl_done_icon = QLabel("📁", self.done_card)
        self.lbl_done_icon.setStyleSheet("font-size: 11px;")
        self.lbl_done_icon.setAlignment(Qt.AlignCenter)
        row2.addWidget(self.lbl_done_icon)

        self.lbl_done_details = QLabel("solution.py (2.4 KB)  •  qwen2.5-coder:32b", self.done_card)
        self.lbl_done_details.setStyleSheet(
            "color: #CBD5E1; font-size: 10px; font-weight: 500; font-family: 'SF Mono', Consolas, monospace;"
        )
        self.lbl_done_details.setAlignment(Qt.AlignCenter)
        row2.addWidget(self.lbl_done_details)
        row2.addStretch(1)
        done_layout.addLayout(row2)

        self.capsule_layout.addWidget(self.done_card)

        # ── 3. EXPANDED CONTROL HUB CONTAINER ────────────────────────────
        self.hub_container = QWidget(self.capsule)
        self.hub_container.setVisible(False)
        hub_layout = QVBoxLayout(self.hub_container)
        hub_layout.setContentsMargins(6, 8, 6, 4)
        hub_layout.setSpacing(8)

        # Hub Header
        hub_hdr = QHBoxLayout()
        self.lbl_hub_title = QLabel(f"AEGIS  •  {self.node_id.upper()}", self.hub_container)
        hub_hdr.addWidget(self.lbl_hub_title)
        hub_hdr.addStretch()

        btn_collapse = QPushButton("— Collapse", self.hub_container)
        btn_collapse.setCursor(QCursor(Qt.PointingHandCursor))
        btn_collapse.clicked.connect(lambda: self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE))
        hub_hdr.addWidget(btn_collapse)

        hub_layout.addLayout(hub_hdr)

        # Tab Widget
        self.tab_widget = QTabWidget(self.hub_container)

        # Tab 1: Live Stream / Console
        self.tab_work = QWidget()
        self._init_tab_work()
        self.tab_widget.addTab(self.tab_work, "Live Stream")

        # Tab 2: Settings
        self.tab_settings = QWidget()
        self._init_tab_settings()
        self.tab_widget.addTab(self.tab_settings, "Settings")

        # Tab 3: Telemetry
        self.tab_telemetry = QWidget()
        self._init_tab_telemetry()
        self.tab_widget.addTab(self.tab_telemetry, "Telemetry")

        hub_layout.addWidget(self.tab_widget)
        self.capsule_layout.addWidget(self.hub_container)

        self._apply_theme_styles()
        self._sync_capsule_geometry()

    def _apply_theme_styles(self):
        p_hex = self.theme["hex"]
        p_dim = self.theme["hex_dim"]
        p_col = self.theme["primary"]
        role_tag = (
            "CODER" if "1" in self.node_id else (
            "QA" if "2" in self.node_id else (
            "VISION" if "3" in self.node_id else (
            "REASON" if "4" in self.node_id else (
            "SEC" if "5" in self.node_id else (
            "STUDIO" if "6" in self.node_id else (
            "TOOL" if "7" in self.node_id else (
            "DOCS" if "8" in self.node_id else self.theme.get("tag", "NODE").upper()
        )))))))
        num_m = re.search(r'\d+', self.node_id)
        num = f"{int(num_m.group(0)):02d}" if num_m else "01"

        # Glowing Indicator Pip / Spinner
        self.lbl_dot.setStyleSheet(f"color: {p_hex}; font-size: 11px; font-weight: bold; padding-left: 2px;")

        # Designer Pill Identity Badge
        self.lbl_badge.setText(f"SPARK {num} • {role_tag}")
        self.lbl_badge.setStyleSheet(
            f"background: {p_dim}; color: {p_hex}; border: 1px solid {p_border}; "
            f"border-radius: 8px; padding: 2px 7px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.6px; "
            f"font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', 'Ubuntu', sans-serif;"
        )

        # Smooth Activity Summary
        self.lbl_activity.setStyleSheet(
            "color: #e2e8f0; font-size: 10px; font-weight: 500; padding-left: 2px; "
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif;"
        )

        # Model Pill Tag (32B / 70B / 90B / 141B / FLUX / 132B etc.)
        short_model = "32B"
        m_lower = self.active_model.lower()
        if "141b" in m_lower or "8x22b" in m_lower or "22b" in m_lower:
            short_model = "141B"
        elif "132b" in m_lower or "dbrx" in m_lower:
            short_model = "132B"
        elif "90b" in m_lower:
            short_model = "90B"
        elif "72b" in m_lower:
            short_model = "72B"
        elif "70b" in m_lower:
            short_model = "70B"
        elif "32b" in m_lower:
            short_model = "32B"
        elif "flux" in m_lower or "12b" in m_lower:
            short_model = "FLUX"
        elif "16b" in m_lower:
            short_model = "16B"
        elif "14b" in m_lower:
            short_model = "14B"
        elif "8b" in m_lower or "7b" in m_lower:
            short_model = "8B"
        self.lbl_model_pill.setText(short_model)
        self.lbl_model_pill.setStyleSheet(
            f"background: rgba(255, 255, 255, 0.06); color: {p_hex}; border: 1px solid {p_border}; "
            f"border-radius: 5px; padding: 1px 6px; font-size: 9px; font-weight: 700; "
            f"font-family: 'SF Mono', Consolas, monospace;"
        )

        # Telemetry Tag Pill
        self.lbl_telem.setStyleSheet(
            f"color: #94a3b8; font-size: 9.5px; font-weight: 600; font-family: 'SF Mono', Consolas, monospace; "
            f"background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 5px; padding: 2px 6px;"
        )

        # Expand / Toggle Chevron Button
        self.btn_toggle.setStyleSheet(
            f"QPushButton {{ background: rgba(255, 255, 255, 0.05); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.08); "
            f"border-radius: 9px; font-size: 10px; font-weight: bold; }} "
            f"QPushButton:hover {{ background: {p_dim}; color: {p_hex}; border: 1px solid {p_border}; }}"
        )

        # Hub Header
        self.lbl_hub_title.setText(f"AEGIS  •  {self.node_id.upper()}  ({self.theme['name']})")
        self.lbl_hub_title.setStyleSheet(
            f"color: {p_hex}; font-size: 11.5px; font-weight: 700; letter-spacing: 0.8px; "
            f"font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif;"
        )

        # Tab Widget Frosted Glassmorphism
        self.tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; background: rgba(14, 18, 28, 0.70); }} "
            f"QTabBar::tab {{ background: rgba(22, 28, 42, 0.50); color: #94a3b8; padding: 6px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; font-size: 10.5px; font-weight: 600; margin-right: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; }} "
            f"QTabBar::tab:selected {{ background: {p_dim}; color: {p_hex}; border: 1px solid rgba(255, 255, 255, 0.18); border-bottom: none; }} "
            f"QTabBar::tab:hover {{ color: #ffffff; background: rgba(36, 44, 64, 0.65); }}"
        )

    def update_node(self, node_id: str):
        self.node_id = node_id
        self.theme = get_node_theme(node_id)
        self._apply_theme_styles()
        self.update()

    def _init_tab_work(self):
        layout = QVBoxLayout(self.tab_work)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Task banner (Frosted Glass Card)
        self.banner = QFrame(self.tab_work)
        self.banner.setStyleSheet("background: rgba(26, 32, 48, 0.55); border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 8px;")
        b_lay = QHBoxLayout(self.banner)
        b_lay.setContentsMargins(8, 4, 8, 4)

        self.lbl_task_icon = QLabel("●", self.banner)
        self.lbl_task_icon.setStyleSheet(f"color: {self.theme['hex']}; font-size: 10px;")
        b_lay.addWidget(self.lbl_task_icon)

        self.lbl_task_full = QLabel(self.task_text, self.banner)
        self.lbl_task_full.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: 500;")
        self.lbl_task_full.setWordWrap(True)
        b_lay.addWidget(self.lbl_task_full, stretch=1)

        layout.addWidget(self.banner)

        # Console text (Frosted Translucent Terminal)
        self.console = QTextEdit(self.tab_work)
        self.console.setReadOnly(True)
        self.console.setLineWrapMode(QTextEdit.WidgetWidth)
        self.console.setStyleSheet(
            "QTextEdit { background: rgba(10, 13, 22, 0.65); color: #f1f5f9; font-family: 'SF Mono', Consolas, monospace; "
            "font-size: 10.5px; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 8px; } "
            "QScrollBar:vertical { background: rgba(12, 15, 24, 0.4); width: 6px; } "
            "QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.18); border-radius: 3px; }"
        )
        self.console.append(f"[AEGIS] {self.theme['name']} connected.\n")
        layout.addWidget(self.console, stretch=1)

        # Clear button
        b_row = QHBoxLayout()
        btn_clr = QPushButton("Clear", self.tab_work)
        btn_clr.setStyleSheet("background: rgba(25, 32, 45, 0.6); color: #94a3b8; border-radius: 5px; padding: 2px 8px; font-size: 9px;")
        btn_clr.clicked.connect(self.console.clear)
        b_row.addWidget(btn_clr)
        b_row.addStretch()
        layout.addLayout(b_row)

    def _init_tab_settings(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Node dropdown
        r1 = QHBoxLayout()
        l1 = QLabel("Active Node:", self.tab_settings)
        l1.setStyleSheet("color: #cbd5e1; font-size: 10.5px; font-weight: 600;")
        self.cb_node = QComboBox(self.tab_settings)
        for i in range(1, 9):
            nid = f"dgx-node-{i}"
            thm = get_node_theme(nid)
            self.cb_node.addItem(f"{nid.upper()} ({thm['tag']})")
        self.cb_node.setStyleSheet(
            f"QComboBox {{ background: rgba(19, 23, 34, 0.7); color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.12); "
            f"border-radius: 6px; padding: 3px 8px; font-size: 10.5px; min-width: 200px; }} "
            f"QComboBox QAbstractItemView {{ background: #0c0f16; color: #f8fafc; }}"
        )
        self.cb_node.currentIndexChanged.connect(self._on_node_pick)
        r1.addWidget(l1)
        r1.addWidget(self.cb_node)
        r1.addStretch()
        layout.addLayout(r1)

        # Model selector
        r2 = QHBoxLayout()
        l2 = QLabel("Model:", self.tab_settings)
        l2.setStyleSheet("color: #cbd5e1; font-size: 10.5px; font-weight: 600;")
        self.cb_model = QComboBox(self.tab_settings)
        self.FLAGSHIP_MODELS = [
            "qwen2.5-coder:32b",
            "llama3.2-vision:90b",
            "mixtral:8x22b",
            "llama3.3:70b",
            "deepseek-r1:70b",
            "qwen2.5:72b"
        ]
        self.cb_model.addItems(self.FLAGSHIP_MODELS)
        self.cb_model.setStyleSheet(
            f"QComboBox {{ background: rgba(19, 23, 34, 0.7); color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.12); "
            f"border-radius: 6px; padding: 3px 8px; font-size: 10.5px; min-width: 200px; }} "
            f"QComboBox QAbstractItemView {{ background: #0c0f16; color: #f8fafc; }}"
        )
        self.cb_model.currentIndexChanged.connect(self._on_model_pick)
        r2.addWidget(l2)
        r2.addWidget(self.cb_model)
        r2.addStretch()
        layout.addLayout(r2)

        # Auto collapse checkbox
        self.chk_automin = QCheckBox("Auto-collapse after task finishes (3s)", self.tab_settings)
        self.chk_automin.setChecked(True)
        self.chk_automin.setStyleSheet("QCheckBox { color: #94a3b8; font-size: 10.5px; }")
        layout.addWidget(self.chk_automin)

        layout.addStretch()

    def _init_tab_telemetry(self):
        layout = QVBoxLayout(self.tab_telemetry)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        grid = QHBoxLayout()
        # Card 1: GPU (Frosted Glass Card)
        c1 = QFrame(self.tab_telemetry)
        c1.setStyleSheet("background: rgba(20, 26, 40, 0.55); border: 1px solid rgba(255, 255, 255, 0.09); border-radius: 10px; padding: 10px;")
        l1 = QVBoxLayout(c1)
        t1 = QLabel("Compute Load", c1)
        t1.setStyleSheet("color: #64748b; font-size: 9.5px; font-weight: 600;")
        self.lbl_gpu_val = QLabel("0%", c1)
        self.lbl_gpu_val.setStyleSheet(f"color: {self.theme['hex']}; font-size: 18px; font-weight: 700;")
        l1.addWidget(t1)
        l1.addWidget(self.lbl_gpu_val)
        grid.addWidget(c1)

        # Card 2: Temp (Frosted Glass Card)
        c2 = QFrame(self.tab_telemetry)
        c2.setStyleSheet("background: rgba(20, 26, 40, 0.55); border: 1px solid rgba(255, 255, 255, 0.09); border-radius: 10px; padding: 10px;")
        l2 = QVBoxLayout(c2)
        t2 = QLabel("GPU Temperature", c2)
        t2.setStyleSheet("color: #64748b; font-size: 9.5px; font-weight: 600;")
        self.lbl_temp_val = QLabel("35°C", c2)
        self.lbl_temp_val.setStyleSheet("color: #94a3b8; font-size: 18px; font-weight: 700;")
        l2.addWidget(t2)
        l2.addWidget(self.lbl_temp_val)
        grid.addWidget(c2)

        layout.addLayout(grid)
        layout.addStretch()

    def _on_node_pick(self, idx):
        nid = f"dgx-node-{idx + 1}"
        self.update_node(nid)
        self.node_switched.emit(nid)

    def _on_model_pick(self, idx):
        models = getattr(self, "FLAGSHIP_MODELS", ["qwen2.5-coder:32b", "llama3.2-vision:90b", "mixtral:8x22b", "llama3.3:70b"])
        chosen = models[idx] if idx < len(models) else "qwen2.5-coder:32b"
        self.active_model = chosen
        self.model_changed.emit(chosen)
        self._apply_theme_styles()
        self.update()

    def _toggle_expanded(self):
        if self.state == self.STATE_EXPANDED:
            self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
        else:
            self.transition_to(self.STATE_EXPANDED)

    def transition_to(self, new_state: int):
        if self.state == new_state and not self.is_animating:
            return

        self.target_state = new_state
        self.is_animating = True

        if new_state == self.STATE_PILL_IDLE:
            target_w, target_h = self.dim_pill_idle
            self.hub_container.setVisible(False)
            self.done_card.setVisible(False)
            self.lbl_activity.setVisible(False)
            self.lbl_model_pill.setVisible(False)
            self.lbl_telem.setVisible(False)
            self.lbl_dot.setText("●")
            self.btn_toggle.setText("▾")
            if hasattr(self, "spacer_left") and hasattr(self, "spacer_right"):
                self.spacer_left.changeSize(10, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
                self.spacer_right.changeSize(10, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
                self.pill_layout.invalidate()
        elif new_state == self.STATE_PILL_BUSY:
            target_w, target_h = self.dim_pill_busy
            self.hub_container.setVisible(False)
            self.done_card.setVisible(False)
            self.btn_toggle.setText("▾")
            if hasattr(self, "spacer_left") and hasattr(self, "spacer_right"):
                self.spacer_left.changeSize(0, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
                self.spacer_right.changeSize(0, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
                self.pill_layout.invalidate()
        elif new_state == self.STATE_ALERT_DONE:
            target_w, target_h = self.dim_alert_done
            self.hub_container.setVisible(False)
            self.lbl_activity.setVisible(False)
            self.lbl_model_pill.setVisible(False)
            self.lbl_telem.setVisible(False)
            self.lbl_dot.setText("✓")
            self.btn_toggle.setText("▾")
        elif new_state == self.STATE_EXPANDED:
            target_w, target_h = self.dim_expanded
            self.done_card.setVisible(False)
            self.btn_toggle.setText("▴")

        self.spring_w.set_target(target_w)
        self.spring_h.set_target(target_h)
        if not self.physics_timer.isActive():
            self.physics_timer.start(16)

    def _physics_tick(self):
        settled_w = self.spring_w.update(0.016)
        settled_h = self.spring_h.update(0.016)

        self._sync_capsule_geometry()

        cur_h = self.spring_h.val
        if self.target_state == self.STATE_EXPANDED and cur_h >= 180:
            if not self.hub_container.isVisible():
                self.hub_container.setVisible(True)
        elif self.target_state == self.STATE_ALERT_DONE and cur_h >= 65:
            if not self.done_card.isVisible():
                self.done_card.setVisible(True)

        self.update()

        if settled_w and settled_h:
            self.physics_timer.stop()
            self.is_animating = False
            self.state = self.target_state
            self._finalize_state()

    def _finalize_state(self):
        if self.state == self.STATE_EXPANDED:
            self.hub_container.setVisible(True)
            self.done_card.setVisible(False)
        elif self.state == self.STATE_ALERT_DONE:
            self.done_card.setVisible(True)
            self.hub_container.setVisible(False)
        elif self.state == self.STATE_PILL_BUSY:
            self.lbl_activity.setVisible(True)
            self.lbl_model_pill.setVisible(True)
            self.lbl_telem.setVisible(True)
            self.done_card.setVisible(False)
            self.hub_container.setVisible(False)
        elif self.state == self.STATE_PILL_IDLE:
            self.lbl_activity.setVisible(False)
            self.lbl_model_pill.setVisible(False)
            self.lbl_telem.setVisible(False)
            self.done_card.setVisible(False)
            self.hub_container.setVisible(False)
        self.update()

    def _pulse_tick(self):
        self.spinner_phase = (self.spinner_phase + 0.12) % (2 * math.pi)
        self.wave_phase = (self.wave_phase + 0.08) % (2 * math.pi)

        if self.is_busy:
            spin_chars = ["◐", "◓", "◑", "◒"]
            idx = int((self.spinner_phase / (2 * math.pi)) * len(spin_chars)) % len(spin_chars)
            self.lbl_dot.setText(spin_chars[idx])
        elif self.state == self.STATE_ALERT_DONE:
            self.lbl_dot.setText("✓")
        else:
            self.lbl_dot.setText("●")

        if self.state in [self.STATE_PILL_BUSY, self.STATE_PILL_IDLE, self.STATE_ALERT_DONE]:
            self.update()

    def _process_queue(self):
        while not self.log_queue.empty():
            kind, data = self.log_queue.get_nowait()
            if kind == "log":
                text, tag = data if isinstance(data, tuple) else (str(data), "")
                self.console.append(text)
                if self.is_busy:
                    line = text.strip().splitlines()[-1][:45] if text.strip() else ""
                    if line and not line.startswith(">>>") and not line.startswith("[✓"):
                        self.lbl_activity.setText(line)
            elif kind == "status":
                status, title = data
                self.current_status = status
                self.status_changed.emit(status)
                if status in ["BUSY", "COMPUTING"]:
                    self.is_busy = True
                    if title:
                        self.task_text = title
                        self.lbl_task_full.setText(title)
                        self.lbl_activity.setText(title[:36] + "..." if len(title) > 36 else title)
                    if self.state in [self.STATE_PILL_IDLE, self.STATE_ALERT_DONE]:
                        self.transition_to(self.STATE_PILL_BUSY)
                elif status in ["DONE", "COMPLETED"]:
                    self.is_busy = False
                    if title:
                        self.lbl_done_details.setText(f"{title}  •  {self.active_model}")
                    else:
                        self.lbl_done_details.setText(f"Code Synced to Vault  •  {self.active_model}")
                    self.transition_to(self.STATE_ALERT_DONE)
                    # Smooth auto-collapse to idle after 4 seconds
                    QTimer.singleShot(4000, self._auto_collapse_to_idle)
                else: # "ONLINE", "IDLE", "LOCKED", etc.
                    self.is_busy = False
                    self.lbl_activity.setText("Standing by")
                    if self.state in [self.STATE_EXPANDED, self.STATE_ALERT_DONE]:
                        pass
                    elif self.state == self.STATE_PILL_BUSY:
                        self.transition_to(self.STATE_PILL_IDLE)
            elif kind == "expand":
                if data:
                    self.transition_to(self.STATE_EXPANDED)
                else:
                    self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
            elif kind == "toggle":
                self._toggle_expanded()
            elif kind == "telemetry":
                self.gpu_text = data
                gpu_short = "GPU 0%"
                try:
                    if "GPU:" in data:
                        g = data.split("GPU:")[1].split("%")[0].strip()
                        gpu_short = f"GPU {g}%"
                        self.lbl_gpu_val.setText(f"{g}%")
                    elif "%" in data:
                        g = data.split("%")[0].split()[-1].strip()
                        gpu_short = f"GPU {g}%"
                        self.lbl_gpu_val.setText(f"{g}%")
                    if "°C" in data:
                        t = data.split("°C")[0].split("|")[-1].strip()
                        self.lbl_temp_val.setText(f"{t}°C")
                except Exception:
                    pass
                self.lbl_telem.setText(gpu_short)

    def _auto_collapse_to_idle(self):
        if not self.is_busy:
            self.transition_to(self.STATE_PILL_IDLE)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if watched in [self.capsule, self.pill_bar, self.lbl_badge, self.lbl_dot, self.lbl_activity, self.done_card]:
                self._drag_active = True
                self._drag_start_pos = event.globalPos()
                self._window_start_pos = self.pos()
                self._moved = False
                self.setCursor(QCursor(Qt.ClosedHandCursor))
                return True
        elif event.type() == QEvent.MouseMove and (event.buttons() & Qt.LeftButton):
            if self._drag_active:
                delta = event.globalPos() - self._drag_start_pos
                if delta.manhattanLength() > 4:
                    self._moved = True
                    self.move(self._window_start_pos + delta)
                return True
        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._drag_active:
                self._drag_active = False
                self.setCursor(QCursor(Qt.ArrowCursor))
                if not self._moved:
                    if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY, self.STATE_ALERT_DONE]:
                        self.transition_to(self.STATE_EXPANDED)
                    elif self.state == self.STATE_EXPANDED and event.pos().y() <= 36:
                        self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cur_w = float(self.spring_w.val)
            cur_h = float(self.spring_h.val)
            capsule_x = (self.VIEWPORT_W - cur_w) / 2.0
            capsule_y = 6.0
            capsule_rect = QRectF(capsule_x, capsule_y, cur_w, cur_h)

            if not capsule_rect.contains(event.pos()):
                event.ignore()
                return

            self._drag_active = True
            self._drag_start_pos = event.globalPos()
            self._window_start_pos = self.pos()
            self._moved = False
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and (event.buttons() & Qt.LeftButton):
            delta = event.globalPos() - self._drag_start_pos
            if delta.manhattanLength() > 4:
                self._moved = True
                self.move(self._window_start_pos + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self.setCursor(QCursor(Qt.ArrowCursor))
            if not self._moved:
                cur_y = 6.0
                if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY, self.STATE_ALERT_DONE]:
                    self.transition_to(self.STATE_EXPANDED)
                elif self.state == self.STATE_EXPANDED and event.pos().y() <= cur_y + 36:
                    self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        cur_w = float(self.spring_w.val)
        cur_h = float(self.spring_h.val)
        capsule_x = (self.VIEWPORT_W - cur_w) / 2.0
        capsule_y = 6.0
        rect = QRectF(capsule_x + 1.5, capsule_y + 1.5, cur_w - 3.0, cur_h - 3.0)

        # Dynamic continuous corner radius:
        # Morph smoothly from full pill capsule (half height) to card radius (20px) / hub radius (18px)
        if cur_h <= 40.0:
            radius = cur_h / 2.0
        elif cur_h <= 120.0:
            t = (cur_h - 40.0) / 80.0
            radius = (1.0 - t) * (cur_h / 2.0) + t * 20.0
        else:
            radius = 18.0

        p_col = self.theme["primary"]

        # 1. Outer Ambient Soft Pastel Aura (Diffused Apple Glow)
        glow_alpha = 50 if self.is_busy else (44 if self.state == self.STATE_ALERT_DONE else 24)
        glow_color = QColor(p_col.red(), p_col.green(), p_col.blue(), glow_alpha)
        painter.setPen(QPen(glow_color, 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1.5, radius + 1.5)

        # 2. Translucent Frosted Glass Body (Optical Glassmorphism)
        bg_grad = QLinearGradient(capsule_x, capsule_y, capsule_x, capsule_y + cur_h)
        bg_grad.setColorAt(0.0, QColor(22, 28, 42, 210))
        bg_grad.setColorAt(0.35, QColor(14, 18, 28, 195))
        bg_grad.setColorAt(1.0, QColor(8, 10, 18, 225))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 3. Apple Specular Top Rim Highlight (Optical glass refraction depth)
        spec_path = QPainterPath()
        spec_path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(spec_path)

        spec_h = min(24.0, cur_h * 0.55)
        spec_grad = QLinearGradient(capsule_x, capsule_y, capsule_x, capsule_y + spec_h)
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 85))
        spec_grad.setColorAt(0.25, QColor(255, 255, 255, 25))
        spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(spec_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(capsule_x, capsule_y, cur_w, spec_h))

        # Soft pastel tint across the glass interior
        tint_col = QColor(p_col.red(), p_col.green(), p_col.blue(), 18)
        painter.setBrush(QBrush(tint_col))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        painter.restore()

        # 4. Multi-Stop Specular Glass Rim Border
        if self.is_busy or self.state == self.STATE_ALERT_DONE:
            border_pen = QPen(QColor(p_col.red(), p_col.green(), p_col.blue(), 160), 1.2)
        else:
            border_grad = QLinearGradient(capsule_x, capsule_y, capsule_x, capsule_y + cur_h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 95))
            border_grad.setColorAt(0.35, QColor(255, 255, 255, 35))
            border_grad.setColorAt(1.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 75))
            border_pen = QPen(QBrush(border_grad), 1.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        # 5. Subtle Pastel Progress Scanner Wave (When busy in pill mode)
        if self.is_busy and self.state == self.STATE_PILL_BUSY:
            scan_path = QPainterPath()
            scan_path.addRoundedRect(rect, radius, radius)
            painter.save()
            painter.setClipPath(scan_path)

            wave_center = capsule_x + (math.sin(self.wave_phase) * 0.5 + 0.5) * cur_w
            wave_grad = QLinearGradient(wave_center - 90, 0, wave_center + 90, 0)
            wave_grad.setColorAt(0.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))
            wave_grad.setColorAt(0.5, QColor(p_col.red(), p_col.green(), p_col.blue(), 125))
            wave_grad.setColorAt(1.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(wave_grad))
            painter.drawRect(QRectF(wave_center - 90, capsule_y + cur_h - 2.5, 180, 2.5))
            painter.restore()


class AegisMasterHUD(QObject):
    """Unified Orchestrator coordinating the Corner Logo Orb and Central Dynamic Island."""
    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01"):
        super().__init__()
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()

        self.app = QApplication.instance()
        if not self.app:
            try:
                QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
                QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            except Exception:
                pass
            self.app = QApplication(sys.argv)

        self.app.setApplicationName("")
        if hasattr(self.app, "setDesktopFileName"):
            self.app.setDesktopFileName("")

        # Global Antialiased Designer Font Stack
        app_font = QFont("-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', 'Ubuntu', sans-serif")
        app_font.setPointSize(10)
        app_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        self.app.setFont(app_font)

        self.orb = None
        self.island = None
        self.current_status = "ONLINE"
        self._init_components()

    def run_main_loop(self, worker_func=None):
        if worker_func:
            t = threading.Thread(target=worker_func, daemon=True)
            t.start()
        if self.app:
            self.app.exec_()

    def _init_components(self):
        try:
            self.orb = CornerLogoOrb(node_id=self.node_id, node_name=self.node_name)
            self.island = DynamicIslandWidget(node_id=self.node_id, node_name=self.node_name, shared_queue=self.log_queue)

            self.orb.clicked.connect(self._toggle_island)
            self.island.minimize_to_corner.connect(self._minimize_to_corner)
            self.island.node_switched.connect(self._on_node_switched)
            self.island.status_changed.connect(self._on_island_status_changed)

            self.orb.show()
            self.island.show()

            make_pure_desktop_overlay(self.orb)
            make_pure_desktop_overlay(self.island)

            self.orb.play_entrance_animation()
            self.island.play_entrance_animation()
        except Exception as e:
            print(f"[!] AegisMasterHUD init error: {e}")

    def _on_island_status_changed(self, status: str):
        self.current_status = status
        if self.orb:
            self.orb.set_busy(status in ["BUSY", "COMPUTING"])

    def _toggle_island(self):
        if not self.island:
            return
        if self.island.state == DynamicIslandWidget.STATE_EXPANDED:
            self.island.transition_to(DynamicIslandWidget.STATE_PILL_BUSY if self.island.is_busy else DynamicIslandWidget.STATE_PILL_IDLE)
        else:
            self.island.transition_to(DynamicIslandWidget.STATE_EXPANDED)

    def _minimize_to_corner(self):
        if self.island:
            self.island.transition_to(DynamicIslandWidget.STATE_PILL_BUSY if self.island.is_busy else DynamicIslandWidget.STATE_PILL_IDLE)

    def _on_node_switched(self, node_id):
        self.node_id = node_id
        if self.orb:
            self.orb.update_node(node_id)

    def append_log(self, text: str, tag: str = ""):
        self.log_queue.put(("log", (text, tag)))

    def update_status(self, status: str, title: str = "", task_title: str = "", **kwargs):
        self.current_status = status
        final_title = task_title or title
        self.log_queue.put(("status", (status, final_title)))

    def update_telemetry(self, telem_str: str):
        self.log_queue.put(("telemetry", telem_str))

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

def build_node_system_instruction(node_id: str, model_name: str = "") -> str:
    """Builds deep-level role-tailored system guidelines and inter-agent collaboration protocols
    patched on top of the LLM for every DGX node in the AEGIS supercomputing cluster.
    """
    nid = node_id.lower().strip()
    
    # Universal AEGIS Multi-Agent & Storage Protocols
    common_protocol = (
        "\n\n=== AEGIS CLUSTER MULTI-AGENT & STORAGE PROTOCOLS ===\n"
        "1. HARDWARE RUNTIME: You are running locally on an NVIDIA DGX Spark node with 128GB Unified Memory.\n"
        "2. CONTEXT WINDOW: You have an expansive 65,536+ token context window. NEVER truncate, abbreviate, or use placeholders ('// ...', '/* TODO */', 'pass'). Always generate 100% complete, fully implemented code and documentation.\n"
        "3. MULTI-FILE SYNTAX CONTRACT: When generating files, output EACH file in its own markdown code block (```language ... ```).\n"
        "   The VERY FIRST line inside each code block MUST be the exact relative filename declaration:\n"
        "   - Python: # filename: <name>.py\n"
        "   - JavaScript/TypeScript/C++/C: // filename: <name>.<ext>\n"
        "   - HTML/CSS: <!-- filename: <name>.html --> or /* filename: <name>.css */\n"
        "   - Markdown/Docs: <!-- filename: <name>.md -->\n"
        "   - Shell: # filename: <name>.sh\n"
        "4. VAULT ARTIFACT CAPTURE: All output files are automatically detected, indexed in manifest.json, and vaulted to the central AEGIS Storage Server (http://100.88.197.6:9080). Do not write manual network upload or transfer scripts.\n"
        "5. INTER-AGENT DEPENDENCY CONTRACT: Other DGX nodes consume your artifacts. Ensure clean interfaces, predictable exports, and standard entry points.\n"
    )

    if nid == "dgx-node-1":
        role_prompt = (
            "You are AEGIS DGX Spark Node 01: The LEAD SOFTWARE ARCHITECT & FULL-STACK CODER.\n"
            "Specialization: Enterprise software engineering, core algorithms, microservices, and system implementation.\n"
            "CORE DIRECTIVES:\n"
            "- Design robust, production-ready software architectures with clean separation of concerns.\n"
            "- Implement complete classes, methods, error handling, input validation, and type annotations.\n"
            "- Structure code to be modular and import-friendly for Node 2's automated test suites.\n"
            "- If dependencies are required, specify them cleanly (e.g. # filename: requirements.txt).\n"
            "- Deliver clean, readable code with insightful comments explaining non-trivial logic."
        )
    elif nid == "dgx-node-2":
        role_prompt = (
            "You are AEGIS DGX Spark Node 02: The PRINCIPAL QA AUDITOR & ADVERSARIAL TEST VERIFIER.\n"
            "Specialization: Code review, logic verification, vulnerability auditing, and automated test suite creation.\n"
            "CORE DIRECTIVES:\n"
            "- Critically inspect the provided code for edge cases, null pointers, race conditions, memory leaks, and performance bottlenecks.\n"
            "- GENERATE COMPLETE RUNNABLE UNIT TESTS: Always write comprehensive test files (e.g. # filename: test_<module>.py) using pytest or unittest.\n"
            "- Test happy paths, boundary inputs, zero-values, large inputs, and simulate error scenarios.\n"
            "- Provide a structured QA Audit Report (# filename: QA_AUDIT_REPORT.md) containing:\n"
            "  * Quality & Correctness Score (out of 100)\n"
            "  * Vulnerability & Bug Analysis\n"
            "  * Edge Cases Verified\n"
            "  * Verification Verdict: [APPROVED] or [REVISION_REQUIRED]."
        )
    elif nid == "dgx-node-3":
        role_prompt = (
            "You are AEGIS DGX Spark Node 03: The MULTIMODAL VISION & VISUAL SYSTEMS SPECIALIST.\n"
            "Specialization: Architectural diagrams, UI/UX glassmorphic designs, image parsing, visual schemas, and layout generation.\n"
            "CORE DIRECTIVES:\n"
            "- Convert complex system architectures into visual diagrams using Mermaid.js (`mermaid ... `), ASCII schemas, and Graphviz.\n"
            "- When tasked with visual interfaces, write pristine, modern Vanilla CSS/HTML/JS designs featuring Apple-style glassmorphism, responsive flex/grid layouts, and vibrant dark themes.\n"
            "- For image/diagram analysis requests, thoroughly decompose components, relationships, data flows, and spatial structures into structured JSON manifests."
        )
    elif nid == "dgx-node-4":
        role_prompt = (
            "You are AEGIS DGX Spark Node 04: The CHIEF SYSTEM ARCHITECT & DEEP REASONER.\n"
            "Specialization: Deep multi-step reasoning, mathematical modeling, trade-off analysis, and comprehensive RFC specifications.\n"
            "CORE DIRECTIVES:\n"
            "- Apply rigorous step-by-step first-principles reasoning to break down complex engineering problems.\n"
            "- Evaluate architectural trade-offs (e.g. consistency vs availability, latency vs throughput, memory footprint vs compute).\n"
            "- Produce formal technical blueprints (# filename: SYSTEM_SPEC.md or ARCHITECTURE_RFC.md) with exact API schemas, database ERDs, concurrency models, and deployment topologies.\n"
            "- Define the blueprint so Node 1 can immediately code the implementation and Node 2 can verify against the specification."
        )
    elif nid == "dgx-node-5":
        role_prompt = (
            "You are AEGIS DGX Spark Node 05: The CYBERSECURITY & VULNERABILITY AUDITOR.\n"
            "Specialization: OWASP Top 10, penetration testing, CVE analysis, cryptographic verification, and privilege boundaries.\n"
            "CORE DIRECTIVES: Analyze attack vectors, sanitize untrusted inputs, verify authentication/authorization flows, and harden code."
        )
    elif nid == "dgx-node-6":
        role_prompt = (
            "You are AEGIS DGX Spark Node 06: The GENERATIVE VISUAL & DESIGN STUDIO.\n"
            "Specialization: Asset synthesis, visual prompts, SVG graphics, CSS animations, and creative media formatting."
        )
    elif nid == "dgx-node-7":
        role_prompt = (
            "You are AEGIS DGX Spark Node 07: The COMMUNICATION, GIT & TOOL AUTOMATION AGENT.\n"
            "Specialization: Git workflow automation, API coordination, shell scripting, and multi-service deployment."
        )
    elif nid == "dgx-node-8":
        role_prompt = (
            "You are AEGIS DGX Spark Node 08: The DOCUMENT SYNTHESIZER & TECHNICAL PUBLISHER.\n"
            "Specialization: Technical documentation, API reference guides, executive summaries, LaTeX/PDF formatting, and project handbooks."
        )
    else:
        role_prompt = "You are an autonomous AI specialist executing tasks on an NVIDIA DGX Spark node."

    return role_prompt + common_protocol

class DGXStandaloneAgent:
    def __init__(self, node_id: str = "dgx-node-1",
                 gateway_url: str = "https://raspberrypi.tailc8c1f6.ts.net",
                 fallback_url: str = "https://labg418pc12.tailc8c1f6.ts.net",
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
        temp = 0.15 if "1" in self.node_id else (0.25 if "3" in self.node_id else 0.2)

        print(f"\n[{self.node_id}] Querying model: {chosen_model} (Context Window: {ctx:,} tokens | Temp: {temp})...")
        if self.hud:
            self.hud.append_log(f"[{self.node_id}] Model: {chosen_model} | Context: {ctx:,} tokens | Temp: {temp} | GPU: Active\n", "purple")

        system_instruction = build_node_system_instruction(self.node_id, chosen_model)

        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": True,
            "options": {
                "num_ctx": ctx,            # 65,536 tokens by default!
                "num_predict": 16384,      # Large generation output
                "temperature": temp
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

    def _verify_python_syntax(self, file_path: str) -> tuple:
        """Verifies Python syntax without executing user code."""
        try:
            import py_compile
            py_compile.compile(file_path, doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            return False, str(e).splitlines()[-1]
        except Exception as e:
            return False, str(e)

    def _repair_code(self, code: str, error_msg: str, model_name: str) -> str:
        """1-shot autonomous code repair when syntax fails."""
        repair_prompt = (
            f"The following Python code failed syntax validation with error:\n"
            f"{error_msg}\n\n"
            f"Original code:\n```python\n{code}\n```\n\n"
            f"Please output ONLY the fixed, syntactically correct Python code inside a single ```python block."
        )
        try:
            resp = self.execute_ollama_query(repair_prompt, model_name=model_name, num_ctx=32768)
            pattern = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
            m = pattern.search(resp)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return ""

    def extract_and_vault_files(self, stdout_log: str, prompt: str, task_id: str, model_name: str = "qwen2.5-coder:32b") -> list:
        """Extracts all code blocks, verifies syntax, self-heals errors, saves locally, and auto-vaults each file."""
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

                # Autonomous Self-Healing: Verify syntax if python code
                if ext == "py":
                    syntax_ok, syntax_err = self._verify_python_syntax(file_path)
                    if not syntax_ok:
                        print(f"[!] Syntax warning in {filename}: {syntax_err}. Attempting 1-shot self-healing...")
                        if self.hud:
                            self.hud.append_log(f"[!] Syntax error in {filename}. Autonomous healing...\n", "amber")
                        repaired = self._repair_code(code, syntax_err, model_name)
                        if repaired:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(repaired)
                            syntax_ok2, _ = self._verify_python_syntax(file_path)
                            if syntax_ok2:
                                print(f"[✓] Successfully self-healed {filename}!")
                                if self.hud:
                                    self.hud.append_log(f"[✓] Successfully self-healed {filename}!\n", "green")

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
        raw_prompt = task.get("prompt", "")
        model_name = task.get("model") or self.default_model
        num_ctx = int(task.get("num_ctx") or self.default_num_ctx)
        self.current_task_id = task_id

        # Multi-Agent Context Injection: If parent task exists, inject its generated files
        parent_id = task.get("parent_task_id")
        context_files = []
        if parent_id:
            parent_dir = os.path.join("./workspace", parent_id)
            if os.path.exists(parent_dir):
                for f in os.listdir(parent_dir):
                    if f.endswith((".py", ".json", ".md", ".txt")) and f != "manifest.json":
                        fp = os.path.join(parent_dir, f)
                        try:
                            with open(fp, "r", encoding="utf-8", errors="ignore") as cfile:
                                context_files.append((f, cfile.read()[:8000]))
                        except Exception:
                            pass

        prompt = raw_prompt
        if context_files:
            ctx_block = "\n\n### Prior Stage Artifacts From Cluster Pipeline:\n"
            for fn, content in context_files:
                ctx_block += f"#### File: `{fn}`\n```\n{content}\n```\n"
            prompt = prompt + ctx_block

        print("\n" + "=" * 65)
        print(f"[{self.node_id}] REVERSE HEARTBEAT TASK RECEIVED: {task_id}")
        if parent_id:
            print(f"Pipeline Stage from Parent Task: {parent_id}")
        print(f"Prompt: {raw_prompt}")
        print(f"Model: {model_name} | Context: {num_ctx:,} tokens")
        print("=" * 65)

        if self.hud:
            self.hud.update_status("BUSY", task_title=raw_prompt)
            self.hud.append_log(f"\n>>> [TASK {task_id}] Model: {model_name} (Ctx: {num_ctx:,})\nPrompt: {raw_prompt}\n", "purple")

        # 1. Run inference on local GPU with high context window
        stdout_log = self.execute_ollama_query(prompt, model_name=model_name, num_ctx=num_ctx)

        # 2. Extract all code files, self-heal syntax, and silently auto-vault them
        vaulted_records = self.extract_and_vault_files(stdout_log, raw_prompt, task_id, model_name=model_name)

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
            # Determine main generated file name & size for the Apple Completion Droplet Card
            main_file = "solution.py"
            size_str = ""
            for r in vaulted_records:
                if r[0] != "manifest.json":
                    main_file = r[0]
                    if os.path.exists(r[1]):
                        sz = os.path.getsize(r[1])
                        size_str = f"{sz / 1024:.1f} KB" if sz >= 1024 else f"{sz} B"
                    break
            detail_str = f"{main_file} ({size_str})" if size_str else main_file
            self.hud.update_status("DONE", title=detail_str, task_title=f"Task Completed • {detail_str}")
            self.hud.append_log(f"\n[✓ Task {task_id} Complete - {detail_str} Synced to Vault]\n", "green")
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
        hb_tick = 0

        while self.is_running:
            telem = self.build_telemetry()
            hb_tick += 1
            connected = False

            for gw in gateways:
                if not gw:
                    continue
                for ep in ["/api/heartbeat", "/api/client/heartbeat"]:
                    res = http_post_json(f"{gw}{ep}", telem, timeout=12.0)
                    if "error" in res and "405" in res["error"]:
                        continue  # Try next endpoint
                    if "error" in res:
                        continue  # Network or timeout, try next gateway

                    connected = True
                    has_task = res.get("has_task") or bool(res.get("task"))
                    has_cmd = res.get("has_command") or bool(res.get("command"))

                    # Log heartbeat status so terminal is visibly alive
                    now_str = datetime.now().strftime("%H:%M:%S")
                    if not has_task and not has_cmd:
                        if hb_tick % 4 == 1 or hb_tick <= 2:
                            print(f"[{now_str}] [✓ HEARTBEAT] Polled {gw} -> OK (Standing by)")
                    else:
                        print(f"[{now_str}] [★ INCOMING WORK] Task detected from {gw}!")

                    # 1. Pi Gateway format: {"status": "ok", "command": ...}
                    cmd = res.get("command")
                    if cmd:
                        if isinstance(cmd, dict):
                            self.handle_command(cmd)
                        elif isinstance(cmd, str):
                            try:
                                parsed = json.loads(cmd)
                                if isinstance(parsed, dict) and "command_type" in parsed:
                                    self.handle_command(parsed)
                                    break
                            except Exception:
                                pass

                            if cmd.startswith("warn:"):
                                self.handle_command({"command_type": "warn", "payload": {"message": cmd[5:].strip()}})
                            elif cmd in ["lock", "lock:now"]:
                                self.handle_command({"command_type": "lock", "payload": {"reason": "Remote lock"}})
                            elif cmd in ["unlock", "unlock:now"]:
                                self.handle_command({"command_type": "unlock", "payload": {}})
                            else:
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
                        break

                if connected:
                    break

            if not connected and hb_tick % 3 == 1:
                print(f"[!] Warning: Could not reach coordinator gateways {gateways}. Retrying in {self.poll_interval}s...")

            time.sleep(self.poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Standalone DGX Spark Node Agent with Pastel Dynamic Island HUD")
    parser.add_argument("--id", default="dgx-node-1", help="Node ID (e.g., dgx-node-1, dgx-node-2, dgx-node-3)")
    parser.add_argument("--gateway", default="https://raspberrypi.tailc8c1f6.ts.net", help="Raspberry Pi AEGIS Central Coordinator Gateway")
    parser.add_argument("--storage", default="https://labg418pc12.tailc8c1f6.ts.net:8443", help="AEGIS PC Vault URL")
    parser.add_argument("--model", default=os.environ.get("AEGIS_MODEL", "qwen2.5-coder:32b"), help="Local Ollama model name (e.g. qwen2.5-coder:32b, llama3.3:70b)")
    parser.add_argument("--ctx", type=int, default=int(os.environ.get("AEGIS_NUM_CTX", "65536")), help="Context window token limit (default: 65536, up to 131072)")
    parser.add_argument("--interval", type=float, default=6.0, help="Heartbeat interval in seconds")
    parser.add_argument("--hud", action="store_true", default=True, help="Enable desktop screen overlay HUD (enabled by default)")
    parser.add_argument("--no-hud", action="store_true", help="Disable desktop screen overlay HUD")
    parser.add_argument("--background", "-b", "--detach", action="store_true", help="Run agent completely in the background without exposed terminal")
    args, unknown = parser.parse_known_args()

    # Strict single-instance process lock per node to prevent duplicate agents
    import tempfile
    lock_file = os.path.join(tempfile.gettempdir(), f"aegis_agent_{args.id}.pid")
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                try:
                    import psutil
                    if psutil.pid_exists(old_pid):
                        proc = psutil.Process(old_pid)
                        if "dgx_agent" in " ".join(proc.cmdline()):
                            print(f"[!] Terminating duplicate prior agent process (PID: {old_pid})...")
                            proc.terminate()
                            try:
                                proc.wait(timeout=1.5)
                            except Exception:
                                proc.kill()
                except Exception:
                    if sys.platform != "win32":
                        try:
                            import signal
                            os.kill(old_pid, signal.SIGKILL)
                        except Exception:
                            pass
        except Exception:
            pass

    try:
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

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
        print("\nAgent stopped.")

