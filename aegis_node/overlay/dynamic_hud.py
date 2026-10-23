"""AEGIS Minimal Dynamic Island & Floating Corner HUD (Apple-Inspired Pastel Edition).
Features:
- Minimal Apple-style Dynamic Island Notch anchored at top-center.
- Ultra-compact idle capsule (e.g. 240 x 36 px) with soft rounded edges.
- Smooth expansion/stretch when active/busy (e.g. 520 x 50 px) showing live task stream & model tag.
- Full Glassmorphic Control Hub (680 x 450 px) when clicked or opened from corner orb.
- Corner Floating Orb (compact 62px) in bottom-right corner to summon / toggle the island.
- Curated soft pastel color palette per DGX node (Lavender for Node 1, Sky for Node 2, Mint for Node 3, etc.).
- Soft Apple/Inter typography, zero harsh neons, zero external branding.
"""
import sys
import os
import math
import queue
import threading
import subprocess
from typing import Optional, Dict, Any

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QRectF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QRadialGradient,
    QLinearGradient, QPainterPath, QCursor, QFontMetrics
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QPushButton, QComboBox,
    QCheckBox, QTabWidget, QGraphicsDropShadowEffect
)

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


def make_pure_desktop_overlay(widget):
    """Ensures widget behaves as a pure desktop overlay, 100% invisible to taskbars, docks, and Alt-Tab."""
    if sys.platform != "win32":
        try:
            win_id = int(widget.winId())
            # Skip taskbar, skip pager, always stay above all application windows
            subprocess.run([
                "xprop", "-id", str(win_id),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_SKIP_TASKBAR, _NET_WM_STATE_SKIP_PAGER, _NET_WM_STATE_ABOVE"
            ], capture_output=True, timeout=0.8)
            # Use UTILITY window type so GNOME Mutter does NOT treat it as a dock or tile it
            subprocess.run([
                "xprop", "-id", str(win_id),
                "-f", "_NET_WM_WINDOW_TYPE", "32a",
                "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_UTILITY"
            ], capture_output=True, timeout=0.8)
            try:
                subprocess.run([
                    "xdotool", "windowmove", str(win_id), str(widget.x()), str(widget.y())
                ], capture_output=True, timeout=0.8)
            except Exception:
                pass
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

        # Pure desktop overlay flags: completely immune to taskbars and dock apps
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "BypassWindowManagerHint"):
            flags |= Qt.BypassWindowManagerHint
        if sys.platform != "win32" and hasattr(Qt, "X11BypassWindowManagerHint"):
            flags |= Qt.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
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
        screen = QApplication.primaryScreen().availableGeometry()
        margin_x = 24
        margin_y = 24
        pos_x = screen.x() + screen.width() - self.orb_size - margin_x
        pos_y = screen.y() + screen.height() - self.orb_size - margin_y
        self.move(pos_x, pos_y)

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

        # 2. Sleek Dark Glass Body
        body_grad = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.2)
        body_grad.setColorAt(0.0, QColor(24, 28, 38, 245))
        body_grad.setColorAt(0.7, QColor(14, 17, 24, 250))
        body_grad.setColorAt(1.0, QColor(9, 12, 17, 255))
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


class DynamicIslandWidget(QWidget):
    """Central Apple-Style Dynamic Island Notch with Smooth Pastel Transitions.
    States:
    1. STATE_PILL_IDLE:  Compact ~240 x 36 px minimal resting capsule at top-center.
    2. STATE_PILL_BUSY:  Horizontally stretched ~540 x 36 px (SAME HEIGHT!) with live activity & wave.
    3. STATE_ALERT_DONE: Downward stretched ~440 x 96 px notification card with tick & file details.
    4. STATE_EXPANDED:   Full ~680 x 440 px elegant frosted developer hub & telemetry console.
    """
    minimize_to_corner = pyqtSignal()
    node_switched = pyqtSignal(str)
    model_changed = pyqtSignal(str)

    STATE_PILL_IDLE = 0
    STATE_PILL_BUSY = 1
    STATE_ALERT_DONE = 2
    STATE_EXPANDED = 3

    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", shared_queue=None, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.theme = get_node_theme(self.node_id)
        self.log_queue = shared_queue or queue.Queue()

        self.state = self.STATE_PILL_IDLE
        self.current_status = "ONLINE"
        self.active_model = "qwen2.5-coder:32b"
        self.task_text = "Ready • Standing by"
        self.gpu_text = "GPU 0%"
        self.is_busy = False

        # Authentic Apple Dynamic Island Dimensions
        self.dim_pill_idle = (240, 36)
        self.dim_pill_busy = (540, 36)    # EXACT SAME 36px HEIGHT!
        self.dim_alert_done = (440, 96)   # Downward stretch droplet card
        self.dim_expanded = (680, 440)

        self.cur_w, self.cur_h = self.dim_pill_idle
        self.start_w, self.start_h = self.cur_w, self.cur_h
        self.target_w, self.target_h = self.cur_w, self.cur_h

        # Window Flags: Pure desktop overlay immune to dock and taskbar
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "BypassWindowManagerHint"):
            flags |= Qt.BypassWindowManagerHint
        if sys.platform != "win32" and hasattr(Qt, "X11BypassWindowManagerHint"):
            flags |= Qt.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus, True)
        self.setMouseTracking(True)
        self.setFixedSize(self.cur_w, self.cur_h)

        # Smooth Ease-In Ease-Out animation
        self.is_animating = False
        self.anim_step = 0
        self.anim_total = 24
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animation_tick)

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
        self._reposition_center()

    def update_node(self, node_id: str):
        self.node_id = node_id
        self.theme = get_node_theme(node_id)
        self._apply_theme_styles()
        self.update()

    def _reposition_center(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.geometry()
        avail = screen.availableGeometry()
        # Physical monitor horizontal center (unaffected by side docks)
        pos_x = geom.x() + int((geom.width() - self.cur_w) / 2)
        # Anchor cleanly beneath GNOME top bar or top screen margin
        pos_y = avail.y() + (6 if avail.y() > geom.y() else 10)
        self.move(pos_x, pos_y)

    def play_entrance_animation(self):
        geom = QApplication.primaryScreen().geometry()
        avail = QApplication.primaryScreen().availableGeometry()
        self.final_y = avail.y() + (6 if avail.y() > geom.y() else 10)
        self.entrance_start_w = 70
        self.entrance_target_w = self.cur_w

        # Position at top-center with mini hardware notch width
        pos_x = geom.x() + int((geom.width() - self.entrance_start_w) / 2)
        self.cur_w = self.entrance_start_w
        self.setFixedSize(self.cur_w, self.cur_h)
        self.move(pos_x, self.final_y)

        self.entrance_step = 0
        self.entrance_total = 24
        self.entrance_timer = QTimer(self)
        self.entrance_timer.timeout.connect(self._entrance_tick)
        self.entrance_timer.start(16)

    def _entrance_tick(self):
        self.entrance_step += 1
        t = self.entrance_step / float(self.entrance_total)
        ease = ease_in_out(t)
        cur_w = int(self.entrance_start_w + (self.entrance_target_w - self.entrance_start_w) * ease)
        geom = QApplication.primaryScreen().geometry()
        pos_x = geom.x() + int((geom.width() - cur_w) / 2)
        self.cur_w = cur_w
        self.setFixedSize(cur_w, self.cur_h)
        self.move(pos_x, self.final_y)
        if self.entrance_step >= self.entrance_total:
            self.entrance_timer.stop()
            self.cur_w = self.entrance_target_w
            self.setFixedSize(self.cur_w, self.cur_h)
            self._reposition_center()
            self.update()

    def _init_ui(self):
        self.master_layout = QVBoxLayout(self)
        self.master_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.master_layout.setContentsMargins(10, 4, 10, 4)
        self.master_layout.setSpacing(0)

        # ── 1. COMPACT IDLE & HORIZONTALLY STRETCHED BUSY CAPSULE (Height 28px inside 36px) ──
        self.pill_bar = QWidget(self)
        self.pill_bar.setFixedHeight(28)
        pill_layout = QHBoxLayout(self.pill_bar)
        pill_layout.setContentsMargins(2, 0, 2, 0)
        pill_layout.setSpacing(8)

        # Left: Soft Pastel Indicator Dot / Spinner / Checkmark
        self.lbl_dot = QLabel("●", self.pill_bar)
        pill_layout.addWidget(self.lbl_dot)

        # Center Identity Badge (SPARK 02 • QA)
        self.lbl_badge = QLabel(self.pill_bar)
        pill_layout.addWidget(self.lbl_badge)

        # Activity summary label (Hidden in Idle, visible when horizontally stretched)
        self.lbl_activity = QLabel(self.task_text, self.pill_bar)
        self.lbl_activity.setVisible(False)
        pill_layout.addWidget(self.lbl_activity, stretch=1)

        # Model Pill Badge (e.g. 32B, visible when stretched)
        self.lbl_model_pill = QLabel("32B", self.pill_bar)
        self.lbl_model_pill.setVisible(False)
        pill_layout.addWidget(self.lbl_model_pill)

        # Telemetry info (Hidden in Idle, visible when stretched)
        self.lbl_telem = QLabel(self.gpu_text, self.pill_bar)
        self.lbl_telem.setVisible(False)
        pill_layout.addWidget(self.lbl_telem)

        # Soft Expand Arrow / Toggle
        self.btn_toggle = QPushButton("▾", self.pill_bar)
        self.btn_toggle.setFixedSize(18, 18)
        self.btn_toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_toggle.clicked.connect(self._toggle_expanded)
        pill_layout.addWidget(self.btn_toggle)

        self.master_layout.addWidget(self.pill_bar)

        # ── 2. TASK DONE NOTIFICATION DROPLET CARD (Drops Down) ──────────
        self.done_card = QWidget(self)
        self.done_card.setVisible(False)
        done_layout = QVBoxLayout(self.done_card)
        done_layout.setContentsMargins(6, 4, 6, 6)
        done_layout.setSpacing(4)

        # Row 1: Checkmark + "TASK COMPLETED • SYNCED TO VAULT"
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)

        self.lbl_done_tick = QLabel("✓", self.done_card)
        self.lbl_done_tick.setStyleSheet("color: #34D399; font-size: 13px; font-weight: 900;")
        row1.addWidget(self.lbl_done_tick)

        self.lbl_done_header = QLabel("TASK COMPLETED • SYNCED TO VAULT", self.done_card)
        self.lbl_done_header.setStyleSheet(
            "color: #F8FAFC; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; "
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif;"
        )
        row1.addWidget(self.lbl_done_header)
        row1.addStretch()
        done_layout.addLayout(row1)

        # Row 2: File Icon + Details
        row2 = QHBoxLayout()
        row2.setContentsMargins(4, 0, 0, 0)
        row2.setSpacing(6)

        self.lbl_done_icon = QLabel("📁", self.done_card)
        self.lbl_done_icon.setStyleSheet("font-size: 11px;")
        row2.addWidget(self.lbl_done_icon)

        self.lbl_done_details = QLabel("solution.py (2.4 KB)  •  qwen2.5-coder:32b", self.done_card)
        self.lbl_done_details.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: 500; font-family: 'SF Mono', Consolas, monospace;"
        )
        row2.addWidget(self.lbl_done_details)
        row2.addStretch()
        done_layout.addLayout(row2)

        self.master_layout.addWidget(self.done_card)

        # ── 3. EXPANDED CONTROL HUB CONTAINER ────────────────────────────
        self.hub_container = QWidget(self)
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
        self.master_layout.addWidget(self.hub_container)

        self._apply_theme_styles()

    def _apply_theme_styles(self):
        p_hex = self.theme["hex"]
        p_dim = self.theme["hex_dim"]
        p_col = self.theme["primary"]
        p_border = f"rgba({p_col.red()}, {p_col.green()}, {p_col.blue()}, 0.38)"
        role_tag = "CODER" if "1" in self.node_id else ("QA/REVIEW" if "2" in self.node_id else self.theme.get("tag", "NODE").upper())
        num = "01" if "1" in self.node_id else ("02" if "2" in self.node_id else self.node_id.replace("dgx-node-", ""))

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

        # Model Pill Tag (32B / 70B etc.)
        short_model = "32B"
        if "70b" in self.active_model.lower():
            short_model = "70B"
        elif "16b" in self.active_model.lower():
            short_model = "16B"
        elif "8x22b" in self.active_model.lower():
            short_model = "22B"
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

        # Tab Widget
        self.tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; background: rgba(12, 16, 24, 0.95); }} "
            f"QTabBar::tab {{ background: rgba(20, 25, 36, 0.6); color: #94a3b8; padding: 6px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; font-size: 10.5px; font-weight: 600; margin-right: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; }} "
            f"QTabBar::tab:selected {{ background: {p_dim}; color: {p_hex}; border: 1px solid rgba(255, 255, 255, 0.12); border-bottom: none; }} "
            f"QTabBar::tab:hover {{ color: #ffffff; background: rgba(30, 38, 54, 0.7); }}"
        )

    def _init_tab_work(self):
        layout = QVBoxLayout(self.tab_work)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Task banner
        self.banner = QFrame(self.tab_work)
        self.banner.setStyleSheet("background: rgba(22, 27, 38, 0.6); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 6px;")
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

        # Console text
        self.console = QTextEdit(self.tab_work)
        self.console.setReadOnly(True)
        self.console.setLineWrapMode(QTextEdit.WidgetWidth)
        self.console.setStyleSheet(
            "QTextEdit { background: #080a0f; color: #e2e8f0; font-family: 'SF Mono', Consolas, monospace; "
            "font-size: 10.5px; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 6px; } "
            "QScrollBar:vertical { background: #0c0f16; width: 6px; } "
            "QScrollBar::handle:vertical { background: #1e2533; border-radius: 3px; }"
        )
        self.console.append(f"[AEGIS] {self.theme['name']} connected.\n")
        layout.addWidget(self.console, stretch=1)

        # Clear button
        b_row = QHBoxLayout()
        btn_clr = QPushButton("Clear", self.tab_work)
        btn_clr.setStyleSheet("background: #19202d; color: #94a3b8; border-radius: 5px; padding: 2px 8px; font-size: 9px;")
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
            f"QComboBox {{ background: #131722; color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.1); "
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
        self.cb_model.addItems(["qwen2.5-coder:32b", "llama3.3:70b", "deepseek-coder-v2:16b", "mixtral:8x22b-instruct"])
        self.cb_model.setStyleSheet(
            f"QComboBox {{ background: #131722; color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.1); "
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
        # Card 1: GPU
        c1 = QFrame(self.tab_telemetry)
        c1.setStyleSheet("background: #11151f; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 8px;")
        l1 = QVBoxLayout(c1)
        t1 = QLabel("Compute Load", c1)
        t1.setStyleSheet("color: #64748b; font-size: 9.5px; font-weight: 600;")
        self.lbl_gpu_val = QLabel("0%", c1)
        self.lbl_gpu_val.setStyleSheet(f"color: {self.theme['hex']}; font-size: 18px; font-weight: 700;")
        l1.addWidget(t1)
        l1.addWidget(self.lbl_gpu_val)
        grid.addWidget(c1)

        # Card 2: Temp
        c2 = QFrame(self.tab_telemetry)
        c2.setStyleSheet("background: #11151f; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 8px;")
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
        models = ["qwen2.5-coder:32b", "llama3.3:70b", "deepseek-coder-v2:16b", "mixtral:8x22b-instruct"]
        chosen = models[idx] if idx < len(models) else "qwen2.5-coder:32b"
        self.active_model = chosen
        self.model_changed.emit(chosen)

    def _toggle_expanded(self):
        if self.state == self.STATE_EXPANDED:
            self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE)
        else:
            self.transition_to(self.STATE_EXPANDED)

    def transition_to(self, new_state: int):
        if self.is_animating or self.state == new_state:
            return

        self.is_animating = True
        self.target_state = new_state
        self.anim_step = 0
        self.start_w, self.start_h = self.cur_w, self.cur_h

        # Immediately hide complex child views so shrinking animation stays smooth & clean
        if new_state == self.STATE_PILL_IDLE:
            self.target_w, self.target_h = self.dim_pill_idle
            self.hub_container.setVisible(False)
            self.done_card.setVisible(False)
            self.lbl_activity.setVisible(False)
            self.lbl_model_pill.setVisible(False)
            self.lbl_telem.setVisible(False)
            self.lbl_dot.setText("●")
            self.btn_toggle.setText("▾")
        elif new_state == self.STATE_PILL_BUSY:
            self.target_w, self.target_h = self.dim_pill_busy
            self.hub_container.setVisible(False)
            self.done_card.setVisible(False)
            self.btn_toggle.setText("▾")
        elif new_state == self.STATE_ALERT_DONE:
            self.target_w, self.target_h = self.dim_alert_done
            self.hub_container.setVisible(False)
            self.lbl_activity.setVisible(False)
            self.lbl_model_pill.setVisible(False)
            self.lbl_telem.setVisible(False)
            self.lbl_dot.setText("✓")
            self.btn_toggle.setText("▾")
        elif new_state == self.STATE_EXPANDED:
            self.target_w, self.target_h = self.dim_expanded
            self.done_card.setVisible(False)
            self.btn_toggle.setText("▴")

        self.anim_timer.start(16)

    def _animation_tick(self):
        self.anim_step += 1
        t = self.anim_step / float(self.anim_total)
        # Fluid Ease-In Ease-Out (C2-continuous smootherstep polynomial)
        ease = ease_in_out(t)

        new_w = int(self.start_w + (self.target_w - self.start_w) * ease)
        new_h = int(self.start_h + (self.target_h - self.start_h) * ease)

        if new_w != self.cur_w or new_h != self.cur_h:
            self.cur_w = new_w
            self.cur_h = new_h
            self.setFixedSize(self.cur_w, self.cur_h)
            self._reposition_center()

        if self.anim_step >= self.anim_total:
            self.anim_timer.stop()
            self.is_animating = False
            self.state = self.target_state
            self.cur_w, self.cur_h = self.target_w, self.target_h
            self.setFixedSize(self.cur_w, self.cur_h)
            self._reposition_center()

            if self.state == self.STATE_EXPANDED:
                self.hub_container.setVisible(True)
            elif self.state == self.STATE_ALERT_DONE:
                self.done_card.setVisible(True)
            elif self.state == self.STATE_PILL_BUSY:
                self.lbl_activity.setVisible(True)
                self.lbl_model_pill.setVisible(True)
                self.lbl_telem.setVisible(True)
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
                    if self.state != self.STATE_EXPANDED:
                        self.transition_to(self.STATE_ALERT_DONE)
                        # Apple 3.5s Notification card -> recoil smoothly to thin Idle capsule
                        QTimer.singleShot(3500, self._auto_collapse_to_idle)
                else: # "ONLINE", "IDLE", "LOCKED", etc.
                    self.is_busy = False
                    self.lbl_activity.setText("Standing by")
                    if self.state == self.STATE_PILL_BUSY:
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
                # Extract compact GPU percent for pill mode
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
        if not self.is_busy and self.state == self.STATE_ALERT_DONE:
            self.transition_to(self.STATE_PILL_IDLE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY, self.STATE_ALERT_DONE]:
                self.transition_to(self.STATE_EXPANDED)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(1.5, 1.5, w - 3, h - 3)

        # Dynamic corner radius: Apple pill mode = fully rounded capsule (h/2), Done card = 20px, Hub = 18px
        if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY]:
            radius = h / 2.0
        elif self.state == self.STATE_ALERT_DONE:
            radius = 20.0
        else:
            radius = 18.0

        p_col = self.theme["primary"]

        # 1. Ambient Soft Pastel Aura (Breathes softly on busy / alert done)
        glow_alpha = 36 if self.is_busy else (30 if self.state == self.STATE_ALERT_DONE else 14)
        glow_color = QColor(p_col.red(), p_col.green(), p_col.blue(), glow_alpha)
        painter.setPen(QPen(glow_color, 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        # 2. Dark Frosted Obsidian Glass Body
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(16, 21, 31, 248))
        bg_grad.setColorAt(0.4, QColor(10, 14, 22, 252))
        bg_grad.setColorAt(1.0, QColor(7, 9, 15, 255))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 3. Apple Specular Top Rim Highlight (Optical glass depth)
        spec_path = QPainterPath()
        spec_path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(spec_path)
        spec_grad = QLinearGradient(0, 0, 0, min(14.0, h * 0.45))
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 36))
        spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(spec_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(0, 0, w, 14))
        painter.restore()

        # 4. Delicate Specular Border (Apple pastel style)
        border_col = self.theme["border"] if (self.is_busy or self.state == self.STATE_ALERT_DONE) else QColor(255, 255, 255, 24)
        painter.setPen(QPen(border_col, 1.1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        # 5. Subtle Pastel Progress Scanner Wave (When busy)
        if self.is_busy and self.state == self.STATE_PILL_BUSY:
            scan_path = QPainterPath()
            scan_path.addRoundedRect(rect, radius, radius)
            painter.save()
            painter.setClipPath(scan_path)

            wave_x = (math.sin(self.wave_phase) * 0.5 + 0.5) * w
            wave_grad = QLinearGradient(wave_x - 90, 0, wave_x + 90, 0)
            wave_grad.setColorAt(0.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))
            wave_grad.setColorAt(0.5, QColor(p_col.red(), p_col.green(), p_col.blue(), 110))
            wave_grad.setColorAt(1.0, QColor(p_col.red(), p_col.green(), p_col.blue(), 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(wave_grad))
            painter.drawRect(QRectF(wave_x - 90, h - 2.5, 180, 2.5))
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

        self.app.setApplicationName("AegisOverlay")
        if hasattr(self.app, "setDesktopFileName"):
            self.app.setDesktopFileName("")

        # Global Antialiased Designer Font Stack
        app_font = QFont("-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', 'Ubuntu', sans-serif")
        app_font.setPointSize(10)
        app_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        self.app.setFont(app_font)

        self.orb = None
        self.island = None
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

            self.orb.show()
            self.island.show()

            make_pure_desktop_overlay(self.orb)
            make_pure_desktop_overlay(self.island)

            self.orb.play_entrance_animation()
            self.island.play_entrance_animation()
        except Exception as e:
            print(f"[!] AegisMasterHUD init error: {e}")

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
        final_title = task_title or title
        self.log_queue.put(("status", (status, final_title)))
        if self.orb:
            self.orb.set_busy(status in ["BUSY", "COMPUTING"])

    def update_telemetry(self, telem_str: str):
        self.log_queue.put(("telemetry", telem_str))

    def set_expanded(self, expand: bool):
        self.log_queue.put(("expand", expand))

    def toggle_expand(self):
        self.log_queue.put(("toggle", None))

