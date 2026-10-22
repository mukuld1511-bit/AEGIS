"""AEGIS Dynamic Island & Corner Floating HUD (Parakeet AI Neon Green Edition).
Features:
- Floating Animated Logo in Bottom-Right Corner (Pulsing Neon Green Atom with rotating orbits).
- Central Dynamic Island-like Bar (Pill shape with generous rounded corners).
- Dynamic Resizing based on state (Idle Pill -> Working/Loading Bar -> Maximized Control Hub).
- Work & Console Tab: Live streaming code, syntax colors, and task status.
- Settings & Features Tab: Model switcher, Context slider, Node switcher, Auto-minimize toggle.
- GPU & Telemetry Tab: Live VRAM bar, GPU utilization, temperature meter.
- Smooth 60 FPS cubic easing transitions and glowing neon green specular effects.
"""
import sys
import os
import math
import queue
import threading
from typing import Optional

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

# Color Palette: Parakeet AI Neon Green Dark Mode
COLOR_BG_DARK = QColor(10, 14, 20, 240)          # Frosted Deep Dark Glass
COLOR_CARD_DARK = QColor(17, 24, 34, 230)        # Inner Panel Dark Glass
COLOR_NEON_GREEN = QColor(0, 255, 136, 255)      # Vibrant Electric Neon Green (#00ff88)
COLOR_NEON_GLOW = QColor(5, 242, 146, 180)       # Secondary Neon Mint Glow (#05f292)
COLOR_NEON_DIM = QColor(0, 255, 136, 60)         # Translucent Neon Green
COLOR_NEON_BORDER = QColor(0, 255, 136, 110)     # Glowing Specular Border
COLOR_TEXT_WHITE = QColor(248, 250, 252, 255)    # Crisp White
COLOR_TEXT_DIM = QColor(148, 163, 184, 255)      # Slate Dim
COLOR_TEXT_NEON = QColor(0, 255, 136, 255)       # Neon Green Accent Text
COLOR_ROSE_ALERT = QColor(244, 63, 94, 255)      # Rose Warning


class CornerLogoOrb(QWidget):
    """Floating Animated Logo Orb anchored in the bottom-right corner.
    Features:
    - Glowing multi-ring Neon Green atom with rotating orbital electrons.
    - Smooth breathing pulse effect.
    - Clicking it summons or toggles the central Dynamic Island Bar!
    """
    clicked = pyqtSignal()

    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.orb_size = 88
        self.atom_phase = 0.0
        self.pulse_phase = 0.0
        self.is_busy = False
        self.is_hovered = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.resize(self.orb_size, self.orb_size)

        self._position_in_corner()

        # Dragging support
        self._drag_active = False
        self._drag_pos = QPoint()
        self._moved = False

        # 60 FPS Orbit timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(25)

    def _position_in_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        margin_x = 28
        margin_y = 28
        pos_x = screen.x() + screen.width() - self.orb_size - margin_x
        pos_y = screen.y() + screen.height() - self.orb_size - margin_y
        self.move(pos_x, pos_y)

    def play_entrance_animation(self):
        """Smoothly glides into the bottom-right corner on PC startup / app launch."""
        screen = QApplication.primaryScreen().availableGeometry()
        margin_x = 28
        margin_y = 28
        self.final_x = screen.x() + screen.width() - self.orb_size - margin_x
        self.final_y = screen.y() + screen.height() - self.orb_size - margin_y
        self.start_y = screen.y() + screen.height() + 80
        self.move(self.final_x, self.start_y)

        self.entrance_step = 0
        self.entrance_total = 24
        self.entrance_timer = QTimer(self)
        self.entrance_timer.timeout.connect(self._entrance_tick)
        self.entrance_timer.start(16)

    def _entrance_tick(self):
        self.entrance_step += 1
        t = self.entrance_step / float(self.entrance_total)
        ease = 1.0 - math.pow(1.0 - t, 3)
        cur_y = int(self.start_y + (self.final_y - self.start_y) * ease)
        self.move(self.final_x, cur_y)
        if self.entrance_step >= self.entrance_total:
            self.entrance_timer.stop()

    def _tick(self):
        speed = 0.09 if self.is_busy else 0.04
        self.atom_phase = (self.atom_phase + speed) % (2 * math.pi)
        self.pulse_phase = (self.pulse_phase + 0.06) % (2 * math.pi)
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
        r = (self.orb_size - 16) / 2.0

        # 1. Outer Neon Breathing Halo
        pulse_alpha = int(35 + 25 * math.sin(self.pulse_phase))
        if self.is_hovered:
            pulse_alpha = min(90, pulse_alpha + 35)
        halo_grad = QRadialGradient(cx, cy, r * 1.45)
        halo_grad.setColorAt(0.0, QColor(0, 255, 136, pulse_alpha))
        halo_grad.setColorAt(0.7, QColor(5, 242, 146, int(pulse_alpha * 0.4)))
        halo_grad.setColorAt(1.0, QColor(0, 255, 136, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo_grad))
        painter.drawEllipse(QRectF(cx - r * 1.35, cy - r * 1.35, r * 2.7, r * 2.7))

        # 2. Glassmorphic Sphere Body (Dark Slate with Neon Specular)
        body_grad = QRadialGradient(cx - r * 0.35, cy - r * 0.35, r * 1.25)
        body_grad.setColorAt(0.0, QColor(24, 34, 48, 245))
        body_grad.setColorAt(0.65, QColor(13, 19, 28, 250))
        body_grad.setColorAt(1.0, QColor(8, 12, 18, 255))
        painter.setBrush(QBrush(body_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 3. Glowing Specular Rim
        rim_color = COLOR_NEON_GREEN if (self.is_busy or self.is_hovered) else COLOR_NEON_BORDER
        painter.setPen(QPen(rim_color, 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 4. Triple Rotating Orbits (Electric Neon Green)
        orbits = [-32.0, 28.0, 88.0]
        orbit_colors = [
            QColor(0, 255, 136, 210),
            QColor(5, 242, 146, 190),
            QColor(52, 211, 153, 200)
        ]
        a = r * 0.70
        b = r * 0.26

        for idx, angle_deg in enumerate(orbits):
            rad = math.radians(angle_deg)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            path = QPainterPath()
            steps = 40
            for s in range(steps + 1):
                t = 2 * math.pi * s / float(steps)
                x = cx + a * math.cos(t) * cos_a - b * math.sin(t) * sin_a
                y = cy + a * math.cos(t) * sin_a + b * math.sin(t) * cos_a
                if s == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            painter.setPen(QPen(orbit_colors[idx], 1.3))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

            # Revolving electron
            e_t = self.atom_phase + (idx * (2 * math.pi / 3.0))
            ex = cx + a * math.cos(e_t) * cos_a - b * math.sin(e_t) * sin_a
            ey = cy + a * math.cos(e_t) * sin_a + b * math.sin(e_t) * cos_a

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 255, 136, 255)))
            painter.drawEllipse(QRectF(ex - 2.8, ey - 2.8, 5.6, 5.6))
            painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
            painter.drawEllipse(QRectF(ex - 1.2, ey - 1.2, 2.4, 2.4))

        # 5. Glowing Central Nucleus
        nuc_grad = QRadialGradient(cx, cy, 7.5)
        nuc_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        nuc_grad.setColorAt(0.35, QColor(0, 255, 136, 245))
        nuc_grad.setColorAt(0.75, QColor(5, 242, 146, 180))
        nuc_grad.setColorAt(1.0, QColor(0, 255, 136, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(nuc_grad))
        painter.drawEllipse(QRectF(cx - 7.5, cy - 7.5, 15.0, 15.0))

        # 6. Bottom Status Pip
        pip_col = COLOR_ROSE_ALERT if self.is_busy else COLOR_NEON_GREEN
        pip_y = cy + r - 3.0
        painter.setBrush(QBrush(pip_col))
        painter.drawEllipse(QRectF(cx - 3.5, pip_y, 7.0, 7.0))


class DynamicIslandWidget(QWidget):
    """Central Dynamic Island Bar with Rounded Corners & Dynamic Sizing.
    States:
    1. PILL_IDLE: 490 x 54 px compact island bar at top-center.
    2. PILL_BUSY: 620 x 78 px island bar with animated neon loading spinner & progress wave.
    3. EXPANDED_HUB: 720 x 480 px maximized control hub with Work, Settings, and Telemetry tabs.
    """
    minimize_to_corner = pyqtSignal()
    node_switched = pyqtSignal(str)
    model_changed = pyqtSignal(str)

    STATE_PILL_IDLE = 0
    STATE_PILL_BUSY = 1
    STATE_EXPANDED = 2

    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01", shared_queue=None, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = shared_queue or queue.Queue()

        self.state = self.STATE_PILL_IDLE
        self.current_status = "ONLINE"
        self.active_model = "qwen2.5-coder:32b"
        self.context_tokens = "65,536"
        self.task_text = "Idle • Waiting for assignments"
        self.gpu_text = "GPU 0% • VRAM 0.0/128G • 35°C"
        self.is_busy = False

        # Dimensions
        self.dim_pill_idle = (510, 56)
        self.dim_pill_busy = (640, 80)
        self.dim_expanded = (720, 500)

        self.cur_w, self.cur_h = self.dim_pill_idle
        self.start_w, self.start_h = self.cur_w, self.cur_h
        self.target_w, self.target_h = self.cur_w, self.cur_h

        # Window Flags & Attributes
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Animation states
        self.is_animating = False
        self.anim_step = 0
        self.anim_total = 14
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animation_tick)

        # Loading spinner & wave phases
        self.spinner_phase = 0.0
        self.wave_phase = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse_tick)
        self.pulse_timer.start(25)

        # Queue timer
        self.q_timer = QTimer(self)
        self.q_timer.timeout.connect(self._process_queue)
        self.q_timer.start(30)

        # Build UI Structure
        self._init_ui()
        self._reposition_center()

    def _reposition_center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        pos_x = screen.x() + int((screen.width() - self.cur_w) / 2)
        pos_y = screen.y() + 20
        self.setGeometry(pos_x, pos_y, self.cur_w, self.cur_h)

    def play_entrance_animation(self):
        """Smoothly glides down from above the screen on PC startup / app launch."""
        screen = QApplication.primaryScreen().availableGeometry()
        self.final_x = screen.x() + int((screen.width() - self.cur_w) / 2)
        self.final_y = screen.y() + 20
        self.start_y = screen.y() - self.cur_h - 40
        self.setGeometry(self.final_x, self.start_y, self.cur_w, self.cur_h)

        self.entrance_step = 0
        self.entrance_total = 22
        self.entrance_timer = QTimer(self)
        self.entrance_timer.timeout.connect(self._entrance_tick)
        self.entrance_timer.start(16)

    def _entrance_tick(self):
        self.entrance_step += 1
        t = self.entrance_step / float(self.entrance_total)
        ease = 1.0 - math.pow(1.0 - t, 3)
        cur_y = int(self.start_y + (self.final_y - self.start_y) * ease)
        self.setGeometry(self.final_x, cur_y, self.cur_w, self.cur_h)
        if self.entrance_step >= self.entrance_total:
            self.entrance_timer.stop()

    def _init_ui(self):
        # Master Layout
        self.master_layout = QVBoxLayout(self)
        self.master_layout.setContentsMargins(14, 10, 14, 10)
        self.master_layout.setSpacing(0)

        # 1. PILL HEADER BAR (Always visible, serves as the compact Island Bar)
        self.pill_bar = QWidget(self)
        self.pill_bar.setFixedHeight(36)
        pill_layout = QHBoxLayout(self.pill_bar)
        pill_layout.setContentsMargins(8, 0, 8, 0)
        pill_layout.setSpacing(10)

        # Neon Green Spark Icon + Title
        self.lbl_logo_pill = QLabel("⚛", self.pill_bar)
        self.lbl_logo_pill.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold;")
        pill_layout.addWidget(self.lbl_logo_pill)

        self.lbl_brand = QLabel(f"AEGIS SPARK", self.pill_bar)
        self.lbl_brand.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 800; letter-spacing: 1px;")
        pill_layout.addWidget(self.lbl_brand)

        # Node Badge Pill
        self.lbl_node_badge = QLabel(self.node_id.upper(), self.pill_bar)
        self.lbl_node_badge.setStyleSheet(
            "background: rgba(0, 255, 136, 0.15); color: #00ff88; font-size: 10px; font-weight: bold; "
            "border: 1px solid rgba(0, 255, 136, 0.4); border-radius: 8px; padding: 2px 7px;"
        )
        pill_layout.addWidget(self.lbl_node_badge)

        # Model Tag Pill
        self.lbl_model_pill = QLabel(f"⚡ {self.active_model}", self.pill_bar)
        self.lbl_model_pill.setStyleSheet(
            "background: rgba(255, 255, 255, 0.08); color: #94a3b8; font-size: 10px; font-weight: 600; "
            "border-radius: 8px; padding: 2px 7px;"
        )
        pill_layout.addWidget(self.lbl_model_pill)

        pill_layout.addStretch()

        # Telemetry Pill (GPU & VRAM)
        self.lbl_telem_pill = QLabel(self.gpu_text, self.pill_bar)
        self.lbl_telem_pill.setStyleSheet("color: #38bdf8; font-family: Consolas, monospace; font-size: 10px;")
        pill_layout.addWidget(self.lbl_telem_pill)

        # Status Pill
        self.lbl_status_pill = QLabel("● ONLINE", self.pill_bar)
        self.lbl_status_pill.setStyleSheet(
            "background: rgba(0, 255, 136, 0.2); color: #00ff88; font-size: 10px; font-weight: bold; "
            "border-radius: 8px; padding: 2px 8px;"
        )
        pill_layout.addWidget(self.lbl_status_pill)

        # Expand / Toggle Button
        self.btn_expand_toggle = QPushButton("▾", self.pill_bar)
        self.btn_expand_toggle.setFixedSize(24, 24)
        self.btn_expand_toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_expand_toggle.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.1); color: #00ff88; border: none; border-radius: 12px; font-weight: bold; font-size: 12px; } "
            "QPushButton:hover { background: rgba(0, 255, 136, 0.25); color: #ffffff; }"
        )
        self.btn_expand_toggle.clicked.connect(self._toggle_expanded)
        pill_layout.addWidget(self.btn_expand_toggle)

        self.master_layout.addWidget(self.pill_bar)

        # 2. LOADING & TASK ROW (Visible when busy in pill mode)
        self.loading_panel = QWidget(self)
        self.loading_panel.setFixedHeight(24)
        self.loading_panel.setVisible(False)
        load_layout = QHBoxLayout(self.loading_panel)
        load_layout.setContentsMargins(12, 0, 12, 0)
        load_layout.setSpacing(8)

        self.lbl_spinner = QLabel("◌", self.loading_panel)
        self.lbl_spinner.setStyleSheet("color: #00ff88; font-size: 14px; font-weight: bold;")
        load_layout.addWidget(self.lbl_spinner)

        self.lbl_busy_task = QLabel("Executing Task...", self.loading_panel)
        self.lbl_busy_task.setStyleSheet("color: #e2e8f0; font-size: 10px; font-style: italic;")
        load_layout.addWidget(self.lbl_busy_task)

        load_layout.addStretch()

        self.lbl_ctx_badge = QLabel("65K CTX", self.loading_panel)
        self.lbl_ctx_badge.setStyleSheet(
            "background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 9px; font-weight: bold; "
            "border-radius: 6px; padding: 1px 6px;"
        )
        load_layout.addWidget(self.lbl_ctx_badge)

        self.master_layout.addWidget(self.loading_panel)

        # 3. EXPANDED CONTROL HUB CONTAINER
        self.hub_container = QWidget(self)
        self.hub_container.setVisible(False)
        hub_layout = QVBoxLayout(self.hub_container)
        hub_layout.setContentsMargins(4, 10, 4, 4)
        hub_layout.setSpacing(10)

        # Hub Header Action Row
        hub_header = QHBoxLayout()
        hub_header.setSpacing(8)

        lbl_hub_title = QLabel("⚛  AEGIS MULTI-DGX AUTONOMOUS CONTROL HUB", self.hub_container)
        lbl_hub_title.setStyleSheet("color: #00ff88; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        hub_header.addWidget(lbl_hub_title)

        hub_header.addStretch()

        # Minimize to Corner button
        btn_to_corner = QPushButton("⤓ Corner Orb", self.hub_container)
        btn_to_corner.setCursor(QCursor(Qt.PointingHandCursor))
        btn_to_corner.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.08); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.15); "
            "border-radius: 6px; padding: 3px 8px; font-size: 10px; } "
            "QPushButton:hover { background: rgba(0, 255, 136, 0.2); color: #00ff88; border-color: #00ff88; }"
        )
        btn_to_corner.clicked.connect(self.minimize_to_corner.emit)
        hub_header.addWidget(btn_to_corner)

        # Minimize to Pill button
        btn_to_pill = QPushButton("— Collapse", self.hub_container)
        btn_to_pill.setCursor(QCursor(Qt.PointingHandCursor))
        btn_to_pill.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.08); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.15); "
            "border-radius: 6px; padding: 3px 8px; font-size: 10px; } "
            "QPushButton:hover { background: rgba(255, 255, 255, 0.2); color: #ffffff; }"
        )
        btn_to_pill.clicked.connect(lambda: self.transition_to(self.STATE_PILL_BUSY if self.is_busy else self.STATE_PILL_IDLE))
        hub_header.addWidget(btn_to_pill)

        hub_layout.addLayout(hub_header)

        # Multi-Tab Widget
        self.tab_widget = QTabWidget(self.hub_container)
        self.tab_widget.setStyleSheet(
            "QTabWidget::pane { border: 1px solid rgba(0, 255, 136, 0.25); border-radius: 12px; background: rgba(14, 20, 29, 0.95); } "
            "QTabBar::tab { background: rgba(20, 28, 40, 0.8); color: #94a3b8; padding: 7px 18px; border-top-left-radius: 8px; "
            "border-top-right-radius: 8px; font-size: 11px; font-weight: bold; margin-right: 4px; } "
            "QTabBar::tab:selected { background: rgba(0, 255, 136, 0.18); color: #00ff88; border: 1px solid rgba(0, 255, 136, 0.4); border-bottom: none; } "
            "QTabBar::tab:hover { color: #ffffff; }"
        )

        # TAB 1: WORK & CONSOLE
        self.tab_work = QWidget()
        self._init_tab_work()
        self.tab_widget.addTab(self.tab_work, "⚡ Work & Live Stream")

        # TAB 2: SETTINGS & FEATURES
        self.tab_settings = QWidget()
        self._init_tab_settings()
        self.tab_widget.addTab(self.tab_settings, "⚙ Settings & Features")

        # TAB 3: TELEMETRY & GPU
        self.tab_telemetry = QWidget()
        self._init_tab_telemetry()
        self.tab_widget.addTab(self.tab_telemetry, "📊 GPU & Telemetry")

        hub_layout.addWidget(self.tab_widget)
        self.master_layout.addWidget(self.hub_container)

    def _init_tab_work(self):
        layout = QVBoxLayout(self.tab_work)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Active Task Banner
        self.banner_task = QFrame(self.tab_work)
        self.banner_task.setStyleSheet("background: rgba(20, 30, 44, 0.8); border: 1px solid rgba(0, 255, 136, 0.2); border-radius: 8px;")
        b_layout = QHBoxLayout(self.banner_task)
        b_layout.setContentsMargins(10, 6, 10, 6)

        self.lbl_task_icon = QLabel("⚡", self.banner_task)
        self.lbl_task_icon.setStyleSheet("color: #00ff88; font-size: 14px;")
        b_layout.addWidget(self.lbl_task_icon)

        self.lbl_task_title = QLabel(self.task_text, self.banner_task)
        self.lbl_task_title.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")
        self.lbl_task_title.setWordWrap(True)
        b_layout.addWidget(self.lbl_task_title, stretch=1)

        layout.addWidget(self.banner_task)

        # Terminal Console Output
        self.console_output = QTextEdit(self.tab_work)
        self.console_output.setReadOnly(True)
        self.console_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.console_output.setStyleSheet(
            "QTextEdit { background: #070a0f; color: #a7f3d0; font-family: Consolas, 'JetBrains Mono', monospace; "
            "font-size: 11px; border: 1px solid rgba(0, 255, 136, 0.25); border-radius: 8px; padding: 8px; } "
            "QScrollBar:vertical { background: #0b1017; width: 8px; } "
            "QScrollBar::handle:vertical { background: #1e293b; border-radius: 4px; } "
            "QScrollBar::handle:vertical:hover { background: #00ff88; }"
        )
        self.console_output.append("[AEGIS SPARK NEON SYSTEM ONLINE]\nReady for distributed code generation & review handoffs.\n")
        layout.addWidget(self.console_output, stretch=1)

        # Console Action Bar
        console_btns = QHBoxLayout()
        btn_clear = QPushButton("Clear Console", self.tab_work)
        btn_clear.setStyleSheet("background: #1e293b; color: #94a3b8; border-radius: 6px; padding: 4px 10px; font-size: 10px;")
        btn_clear.clicked.connect(self.console_output.clear)
        console_btns.addWidget(btn_clear)

        console_btns.addStretch()

        self.lbl_word_count = QLabel("Status: Ready", self.tab_work)
        self.lbl_word_count.setStyleSheet("color: #64748b; font-size: 10px;")
        console_btns.addWidget(self.lbl_word_count)

        layout.addLayout(console_btns)

    def _init_tab_settings(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Row 1: Node Switcher
        r1 = QHBoxLayout()
        lbl_node = QLabel("Target DGX Node:", self.tab_settings)
        lbl_node.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: bold;")
        self.cb_node = QComboBox(self.tab_settings)
        self.cb_node.addItems(["dgx-node-1 (Lead Coder - Spark 01)", "dgx-node-2 (Reviewer & QA - Spark 02)"])
        self.cb_node.setStyleSheet(
            "QComboBox { background: #111927; color: #00ff88; border: 1px solid rgba(0, 255, 136, 0.35); "
            "border-radius: 6px; padding: 4px 10px; font-size: 11px; min-width: 260px; } "
            "QComboBox QAbstractItemView { background: #0a0e17; color: #f8fafc; selection-background-color: #00ff88; selection-color: #000000; }"
        )
        self.cb_node.currentIndexChanged.connect(self._on_node_changed)
        r1.addWidget(lbl_node)
        r1.addWidget(self.cb_node)
        r1.addStretch()
        layout.addLayout(r1)

        # Row 2: Model Selector
        r2 = QHBoxLayout()
        lbl_model = QLabel("Local GPU Model:", self.tab_settings)
        lbl_model.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: bold;")
        self.cb_model = QComboBox(self.tab_settings)
        self.cb_model.addItems([
            "qwen2.5-coder:32b (Default 128K Context Leader)",
            "llama3.3:70b (70B Reasoning & Planning)",
            "deepseek-coder-v2:16b (16B Lightweight Coder)",
            "mixtral:8x22b-instruct (141B MoE)"
        ])
        self.cb_model.setStyleSheet(
            "QComboBox { background: #111927; color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); "
            "border-radius: 6px; padding: 4px 10px; font-size: 11px; min-width: 260px; } "
            "QComboBox QAbstractItemView { background: #0a0e17; color: #f8fafc; selection-background-color: #38bdf8; selection-color: #000000; }"
        )
        self.cb_model.currentIndexChanged.connect(self._on_model_changed)
        r2.addWidget(lbl_model)
        r2.addWidget(self.cb_model)
        r2.addStretch()
        layout.addLayout(r2)

        # Row 3: Context Window Tokens
        r3 = QHBoxLayout()
        lbl_ctx = QLabel("Context Window Limit:", self.tab_settings)
        lbl_ctx.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: bold;")
        self.cb_ctx = QComboBox(self.tab_settings)
        self.cb_ctx.addItems(["65,536 tokens (Standard)", "32,768 tokens (Fast)", "131,072 tokens (Full 128K)"])
        self.cb_ctx.setStyleSheet(
            "QComboBox { background: #111927; color: #a7f3d0; border: 1px solid rgba(167, 243, 208, 0.35); "
            "border-radius: 6px; padding: 4px 10px; font-size: 11px; min-width: 260px; }"
        )
        r3.addWidget(lbl_ctx)
        r3.addWidget(self.cb_ctx)
        r3.addStretch()
        layout.addLayout(r3)

        # Row 4: Toggles
        r4 = QHBoxLayout()
        self.chk_automin = QCheckBox("Auto-minimize to Island after idle (4s)", self.tab_settings)
        self.chk_automin.setChecked(True)
        self.chk_automin.setStyleSheet("QCheckBox { color: #cbd5e1; font-size: 11px; } QCheckBox::indicator:checked { background: #00ff88; }")
        r4.addWidget(self.chk_automin)

        self.chk_sound = QCheckBox("Voice Feedback & Audio", self.tab_settings)
        self.chk_sound.setChecked(True)
        self.chk_sound.setStyleSheet("QCheckBox { color: #cbd5e1; font-size: 11px; } QCheckBox::indicator:checked { background: #00ff88; }")
        r4.addWidget(self.chk_sound)
        r4.addStretch()
        layout.addLayout(r4)

        layout.addStretch()

    def _init_tab_telemetry(self):
        layout = QVBoxLayout(self.tab_telemetry)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # VRAM Gauge
        lbl_vram_title = QLabel("NVIDIA Blackwell VRAM Usage (128 GB Unified):", self.tab_telemetry)
        lbl_vram_title.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_vram_title)

        self.vram_bar = QFrame(self.tab_telemetry)
        self.vram_bar.setFixedHeight(22)
        self.vram_bar.setStyleSheet("background: #0f172a; border: 1px solid rgba(0, 255, 136, 0.3); border-radius: 11px;")
        layout.addWidget(self.vram_bar)

        self.lbl_vram_num = QLabel("Allocated: 19.5 GB / 128.0 GB (15%)", self.tab_telemetry)
        self.lbl_vram_num.setStyleSheet("color: #00ff88; font-size: 11px; font-family: Consolas;")
        layout.addWidget(self.lbl_vram_num)

        # GPU Compute Load & Temperature
        telem_grid = QHBoxLayout()
        self.box_gpu = QFrame(self.tab_telemetry)
        self.box_gpu.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 10px;")
        bg_l = QVBoxLayout(self.box_gpu)
        lbl_g_t = QLabel("Compute Utilization", self.box_gpu)
        lbl_g_t.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.lbl_gpu_val = QLabel("14%", self.box_gpu)
        self.lbl_gpu_val.setStyleSheet("color: #38bdf8; font-size: 20px; font-weight: bold;")
        bg_l.addWidget(lbl_g_t)
        bg_l.addWidget(self.lbl_gpu_val)
        telem_grid.addWidget(self.box_gpu)

        self.box_temp = QFrame(self.tab_telemetry)
        self.box_temp.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 10px;")
        bt_l = QVBoxLayout(self.box_temp)
        lbl_t_t = QLabel("GPU Temperature", self.box_temp)
        lbl_t_t.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.lbl_temp_val = QLabel("42°C", self.box_temp)
        self.lbl_temp_val.setStyleSheet("color: #34d399; font-size: 20px; font-weight: bold;")
        bt_l.addWidget(lbl_t_t)
        bt_l.addWidget(self.lbl_temp_val)
        telem_grid.addWidget(self.box_temp)

        layout.addLayout(telem_grid)
        layout.addStretch()

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

        if new_state == self.STATE_PILL_IDLE:
            self.target_w, self.target_h = self.dim_pill_idle
            self.hub_container.setVisible(False)
            self.loading_panel.setVisible(False)
            self.btn_expand_toggle.setText("▾")
        elif new_state == self.STATE_PILL_BUSY:
            self.target_w, self.target_h = self.dim_pill_busy
            self.hub_container.setVisible(False)
            self.loading_panel.setVisible(True)
            self.btn_expand_toggle.setText("▾")
        elif new_state == self.STATE_EXPANDED:
            self.target_w, self.target_h = self.dim_expanded
            self.loading_panel.setVisible(False)
            self.btn_expand_toggle.setText("▴")

        self.anim_timer.start(16)

    def _animation_tick(self):
        self.anim_step += 1
        t = self.anim_step / float(self.anim_total)
        # Ease-out cubic
        ease = 1.0 - math.pow(1.0 - t, 3)

        self.cur_w = int(self.start_w + (self.target_w - self.start_w) * ease)
        self.cur_h = int(self.start_h + (self.target_h - self.start_h) * ease)

        self._reposition_center()

        if self.anim_step >= self.anim_total:
            self.anim_timer.stop()
            self.is_animating = False
            self.state = self.target_state
            if self.state == self.STATE_EXPANDED:
                self.hub_container.setVisible(True)
            elif self.state == self.STATE_PILL_BUSY:
                self.loading_panel.setVisible(True)
            self.update()

    def _pulse_tick(self):
        # Spinner rotation & wave phase
        self.spinner_phase = (self.spinner_phase + 0.12) % (2 * math.pi)
        self.wave_phase = (self.wave_phase + 0.08) % (2 * math.pi)

        # Update spinner character
        spin_chars = ["◐", "◓", "◑", "◒"]
        idx = int((self.spinner_phase / (2 * math.pi)) * len(spin_chars)) % len(spin_chars)
        self.lbl_spinner.setText(spin_chars[idx])

        if self.state in [self.STATE_PILL_BUSY, self.STATE_PILL_IDLE]:
            self.update()

    def _process_queue(self):
        while not self.log_queue.empty():
            kind, data = self.log_queue.get_nowait()
            if kind == "log":
                text, tag = data if isinstance(data, tuple) else (str(data), "")
                self.console_output.append(text)
                if self.state != self.STATE_EXPANDED and self.is_busy:
                    self.lbl_busy_task.setText(text.strip().splitlines()[-1][:60])
            elif kind == "status":
                status, title = data
                self.current_status = status
                self.is_busy = status in ["BUSY", "COMPUTING"]
                self.lbl_status_pill.setText(f"● {status}")

                if self.is_busy:
                    self.lbl_status_pill.setStyleSheet(
                        "background: rgba(244, 63, 94, 0.25); color: #f43f5e; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 2px 8px;"
                    )
                    if title:
                        self.task_text = title
                        self.lbl_task_title.setText(title)
                        self.lbl_busy_task.setText(title[:55])
                    if self.state == self.STATE_PILL_IDLE:
                        self.transition_to(self.STATE_PILL_BUSY)
                else:
                    self.lbl_status_pill.setStyleSheet(
                        "background: rgba(0, 255, 136, 0.2); color: #00ff88; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 2px 8px;"
                    )
                    if self.state == self.STATE_PILL_BUSY:
                        if self.chk_automin.isChecked():
                            QTimer.singleShot(4000, self._auto_collapse)
            elif kind == "telemetry":
                self.gpu_text = data
                self.lbl_telem_pill.setText(data)
                # Parse metrics for telemetry tab
                try:
                    if "GPU:" in data:
                        gpu_pct = data.split("GPU:")[1].split("%")[0].strip()
                        self.lbl_gpu_val.setText(f"{gpu_pct}%")
                    if "Temp:" in data or "°C" in data:
                        t_str = data.split("°C")[0].split("|")[-1].strip()
                        self.lbl_temp_val.setText(f"{t_str}°C")
                except Exception:
                    pass

    def _auto_collapse(self):
        if not self.is_busy and self.state == self.STATE_PILL_BUSY:
            self.transition_to(self.STATE_PILL_IDLE)

    def _on_node_changed(self, idx):
        node = "dgx-node-1" if idx == 0 else "dgx-node-2"
        self.node_id = node
        self.lbl_node_badge.setText(node.upper())
        self.node_switched.emit(node)

    def _on_model_changed(self, idx):
        models = ["qwen2.5-coder:32b", "llama3.3:70b", "deepseek-coder-v2:16b", "mixtral:8x22b-instruct"]
        chosen = models[idx] if idx < len(models) else "qwen2.5-coder:32b"
        self.active_model = chosen
        self.lbl_model_pill.setText(f"⚡ {chosen}")
        self.model_changed.emit(chosen)

    def mousePressEvent(self, event):
        # Click on pill bar toggles expansion
        if event.button() == Qt.LeftButton:
            if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY]:
                self.transition_to(self.STATE_EXPANDED)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(2, 2, w - 4, h - 4)

        # Dynamic corner radius: rounder in pill mode (27px), sleek rounded in hub (22px)
        radius = 27.0 if self.state in [self.STATE_PILL_IDLE, self.STATE_PILL_BUSY] else 22.0

        # 1. Dark Glassmorphic Backdrop
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(12, 17, 25, 245))
        bg_grad.setColorAt(1.0, QColor(7, 10, 16, 252))
        painter.setBrush(QBrush(bg_grad))

        # 2. Specular Neon Green Border
        border_col = COLOR_NEON_GREEN if self.is_busy else COLOR_NEON_BORDER
        painter.setPen(QPen(border_col, 1.6))
        painter.drawRoundedRect(rect, radius, radius)

        # 3. Animated Neon Scanner Wave (When busy)
        if self.is_busy:
            scan_path = QPainterPath()
            scan_path.addRoundedRect(rect, radius, radius)
            painter.save()
            painter.setClipPath(scan_path)

            wave_x = (math.sin(self.wave_phase) * 0.5 + 0.5) * w
            wave_grad = QLinearGradient(wave_x - 120, 0, wave_x + 120, 0)
            wave_grad.setColorAt(0.0, QColor(0, 255, 136, 0))
            wave_grad.setColorAt(0.5, QColor(0, 255, 136, 120))
            wave_grad.setColorAt(1.0, QColor(0, 255, 136, 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(wave_grad))
            painter.drawRect(QRectF(wave_x - 120, h - 3, 240, 3))
            painter.restore()


class AegisMasterHUD(QObject):
    """Unified Orchestrator coordinating the Corner Logo Orb and Central Dynamic Island."""
    def __init__(self, node_id="dgx-node-1", node_name="DGX Spark 01"):
        super().__init__()
        self.node_id = node_id
        self.node_name = node_name
        self.log_queue = queue.Queue()

        self.corner_orb: Optional[CornerLogoOrb] = None
        self.dynamic_island: Optional[DynamicIslandWidget] = None

    def run_main_loop(self, worker_func):
        """Initializes Qt widgets and starts worker polling loop."""
        try:
            app = QApplication.instance()
            if not app:
                app = QApplication([sys.argv[0]])

            # Set modern application font
            font = QFont("Segoe UI", 9)
            font.setStyleStrategy(QFont.PreferAntialias)
            app.setFont(font)

            # 1. Instantiate Floating Corner Logo
            self.corner_orb = CornerLogoOrb(node_id=self.node_id, node_name=self.node_name)
            self.corner_orb.show()
            self.corner_orb.play_entrance_animation()

            # 2. Instantiate Central Dynamic Island
            self.dynamic_island = DynamicIslandWidget(
                node_id=self.node_id,
                node_name=self.node_name,
                shared_queue=self.log_queue
            )
            self.dynamic_island.show()
            self.dynamic_island.play_entrance_animation()

            # Wire click from Corner Orb to toggle Dynamic Island
            self.corner_orb.clicked.connect(self._on_corner_orb_clicked)
            self.dynamic_island.minimize_to_corner.connect(self._on_minimize_to_corner)

            print("[✓] AEGIS Parakeet AI Neon Green Dynamic Island & Floating Corner HUD Active!")

            # Background worker thread for network/heartbeats
            t = threading.Thread(target=worker_func, daemon=True)
            t.start()

            sys.exit(app.exec_())
        except Exception as e:
            print(f"[!] HUD Exception: {e}")
            worker_func()

    def _on_corner_orb_clicked(self):
        if not self.dynamic_island:
            return
        if self.dynamic_island.isVisible():
            if self.dynamic_island.state != DynamicIslandWidget.STATE_EXPANDED:
                self.dynamic_island.transition_to(DynamicIslandWidget.STATE_EXPANDED)
            else:
                self.dynamic_island.transition_to(DynamicIslandWidget.STATE_PILL_IDLE)
        else:
            self.dynamic_island.show()
            self.dynamic_island.transition_to(DynamicIslandWidget.STATE_EXPANDED)

    def _on_minimize_to_corner(self):
        if self.dynamic_island:
            self.dynamic_island.hide()
        if self.corner_orb:
            self.corner_orb.show()

    def append_log(self, text: str, tag: str = ""):
        self.log_queue.put(("log", (text, tag)))

    def update_status(self, status: str, task_title: str = ""):
        self.log_queue.put(("status", (status, task_title)))
        if self.corner_orb:
            self.corner_orb.set_busy(status in ["BUSY", "COMPUTING"])

    def update_telemetry(self, gpu_text: str):
        self.log_queue.put(("telemetry", gpu_text))

    def show_warning(self, msg: str):
        self.append_log(f"\n⚠️ [GATEWAY ALERT] {msg}\n", "rose")

    def set_locked(self, locked: bool, reason: str = ""):
        status = "LOCKED" if locked else "ONLINE"
        self.update_status(status, reason or "Locked by operator")
