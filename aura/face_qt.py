# -*- coding: utf-8 -*-
"""Лицо AURA — это состояние системы. QPainter-анимация.

Состояния: idle, listening, thinking, speaking, success, error, alert, sleep.
Настроение подмешивает оттенок свечения.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

TICK_MS = 33

STATE_COLORS = {
    "idle": (80, 160, 255),
    "listening": (0, 225, 255),
    "thinking": (185, 130, 255),
    "speaking": (60, 255, 190),
    "success": (80, 255, 160),
    "error": (255, 90, 90),
    "alert": (255, 160, 70),
    "sleep": (70, 90, 130),
}
STATE_HOLD = {"success": 2.2, "error": 2.5, "alert": 2.5}


def _rgb(c, a=255):
    return QColor(c[0], c[1], c[2], a)


def _mix(a, b, k):
    return [x + (y - x) * k for x, y in zip(a, b)]


class FaceWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self._state = "idle"
        self._color = list(STATE_COLORS["idle"])
        self._mood_tint = None
        self._phase = 0.0
        self._ripple = 0.0
        self._hold_until = 0.0
        self._resume = "idle"
        self._energy = 87
        self._pupil = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    # ------------------------------------------------------------------
    def set_state(self, name: str):
        if name not in STATE_COLORS:
            return
        now = time.time()
        if self._state in STATE_HOLD and now < self._hold_until and name in (
                "idle", "listening"):
            self._resume = name
            return
        self._state = name
        if name in STATE_HOLD:
            self._hold_until = now + STATE_HOLD[name]

    def set_mood(self, mood: str, energy: float):
        from .mood import MOOD_TINT
        self._mood_tint = MOOD_TINT.get(mood)
        self._energy = energy

    def stop(self):
        self._timer.stop()

    # ------------------------------------------------------------------
    def _tick(self):
        try:
            self.update()
        except Exception:
            self._timer.stop()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            self._draw(p)
        finally:
            p.end()

    def _draw(self, p: QPainter):
        t = time.time()
        w = max(self.width(), 10)
        h = max(self.height(), 10)
        cx, cy = w / 2, h / 2
        R = min(w, h) * 0.30

        state = self._state
        # цвет состояния + настроение
        target = list(STATE_COLORS[state])
        if self._mood_tint and state in ("idle", "sleep"):
            target = _mix(target, list(self._mood_tint), 0.55)
        self._color = _mix(self._color, target, 0.16)
        c = [int(x) for x in self._color]
        col = _rgb(c)
        col_dim = _rgb([int(x * 0.45) for x in c])
        col_deep = _rgb([int(x * 0.16) for x in c], 200)

        breath = 1 + 0.02 * math.sin(t * 1.8)
        pulse = 0.5 + 0.5 * math.sin(t * 4.0)
        R_eff = R * (breath if state != "sleep" else breath * 0.96)
        active = state not in ("off",)

        # --- фоновая заливка и свечение ---
        p.fillRect(0, 0, w, h, QColor("#0a0f1c"))
        grad = QRadialGradient(cx, cy, R_eff * 2.2)
        grad.setColorAt(0.0, _rgb(c, 46))
        grad.setColorAt(0.55, _rgb(c, 14))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R_eff * 2.2, R_eff * 2.2)

        # --- вращающиеся дуги ---
        speed = {"thinking": 2.6, "listening": 1.2, "speaking": 0.9,
                 "success": 1.4}.get(state, 0.35)
        self._phase += speed * TICK_MS / 1000 * math.pi
        p.setBrush(Qt.NoBrush)
        pen = QPen(col, 4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        rr = R_eff * 1.12
        rect = QRectF(cx - rr, cy - rr, rr * 2, rr * 2)
        p.drawArc(rect, int(self._phase * 57.3) % 360 * 16, 250 * 16)
        pen2 = QPen(col_dim, 2)
        p.setPen(pen2)
        rr2 = R_eff * 1.34
        rect2 = QRectF(cx - rr2, cy - rr2, rr2 * 2, rr2 * 2)
        p.drawArc(rect2, int((-self._phase * 1.6) * 57.3) % 360 * 16, 120 * 16)

        # --- волны-сонар при listening ---
        if state == "listening":
            self._ripple = (self._ripple + 0.014) % 1.0
            for i in range(3):
                k = (self._ripple + i / 3) % 1.0
                rw = R_eff * (1.05 + k * 1.05)
                alpha = int((1 - k) * 150)
                if alpha > 8:
                    p.setPen(QPen(_rgb(STATE_COLORS["listening"], alpha), 2))
                    p.drawEllipse(QPointF(cx, cy), rw, rw)

        # --- спутники при thinking ---
        if state == "thinking":
            for i in range(3):
                ang = self._phase * 1.3 + i * 2.09
                dist = R_eff * 1.24
                dx, dy = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(dx, dy), R * 0.05, R * 0.05)

        # --- ядро ---
        p.setBrush(col_deep)
        p.setPen(QPen(col_dim, 1.5))
        rc = R_eff * 0.98 * (1 + 0.04 * pulse if state == "speaking" else 1)
        p.drawEllipse(QPointF(cx, cy), rc, rc)

        # --- глаза ---
        eye_dx = R * 0.38
        eye_y = cy - R * 0.22
        if state == "sleep" or state == "idle":
            # линии-веки на idle смотрят спокойно, круги на idle
            pass
        ew = R * 0.16
        eh = R * 0.22
        glow = 1 + 0.12 * pulse if state in ("listening", "speaking", "alert") else 1
        p.setPen(Qt.NoPen)
        for side in (-1, 1):
            ex = cx + side * eye_dx
            if state == "success":
                # счастливые глаза "^ ^"
                path = QPainterPath()
                path.moveTo(ex - ew, eye_y + eh * 0.35)
                path.quadTo(ex, eye_y - eh * 0.85, ex + ew, eye_y + eh * 0.35)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(col, R * 0.07, Qt.SolidLine, Qt.RoundCap))
                p.drawPath(path)
                p.setBrush(col)
                p.setPen(Qt.NoPen)
            elif state == "error":
                # ×  ×
                p.setPen(QPen(col, R * 0.06, Qt.SolidLine, Qt.RoundCap))
                s = ew * 0.8
                p.drawLine(QPointF(ex - s, eye_y - s), QPointF(ex + s, eye_y + s))
                p.drawLine(QPointF(ex - s, eye_y + s), QPointF(ex + s, eye_y - s))
                p.setPen(Qt.NoPen)
            elif state == "sleep":
                p.setBrush(col_dim)
                p.drawEllipse(QPointF(ex, eye_y), ew * 0.5, max(1.5, eh * 0.06))
            elif state == "thinking":
                # глаза-щёлочки со «бегающими» зрачками
                self._pupil = math.sin(t * 2.6) * ew * 0.5
                p.setBrush(_rgb(c, 70))
                p.drawEllipse(QPointF(ex, eye_y), ew * 1.15, eh * 0.45)
                p.setBrush(col)
                p.drawEllipse(QPointF(ex + self._pupil, eye_y), ew * 0.42, eh * 0.3)
            elif state == "listening":
                # широкие глаза с бликом ◉
                p.setBrush(_rgb(c, 90))
                p.drawEllipse(QPointF(ex, eye_y), ew * 1.35 * glow, eh * 1.2 * glow)
                p.setBrush(col)
                p.drawEllipse(QPointF(ex, eye_y), ew * 0.85, eh * 0.8)
                p.setBrush(QColor(255, 255, 255, 190))
                p.drawEllipse(QPointF(ex - ew * 0.3, eye_y - eh * 0.3),
                              ew * 0.22, eh * 0.2)
            else:
                # спокойные глаза
                p.setBrush(col)
                p.drawEllipse(QPointF(ex, eye_y), ew * glow, eh * glow)

        # --- рот ---
        mouth_y = cy + R * 0.38
        if state == "speaking":
            bars, span, bw = 14, R * 1.1, R * 0.05
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            for i in range(bars):
                x = cx - span / 2 + span * i / (bars - 1)
                wob = abs(math.sin(t * 9 + i * 1.7)) * (0.35 + 0.65 * abs(math.sin(t * 3.1 + i)))
                bh = R * 0.22 * (0.15 + 0.85 * wob)
                p.drawRoundedRect(QRectF(x - bw / 2, mouth_y - bh, bw, bh * 2), bw, bw)
        elif state == "success":
            path = QPainterPath()
            path.moveTo(cx - R * 0.3, mouth_y - R * 0.05)
            path.quadTo(cx, mouth_y + R * 0.28, cx + R * 0.3, mouth_y - R * 0.05)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, R * 0.06, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
        elif state == "listening":
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, mouth_y), R * 0.08 * (1 + 0.2 * pulse),
                          R * 0.12 * (1 + 0.2 * pulse))
        elif state in ("error", "alert"):
            p.setPen(QPen(col, R * 0.05, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - R * 0.22, mouth_y), QPointF(cx + R * 0.22, mouth_y))
        elif state == "sleep":
            p.setPen(QPen(col_dim, R * 0.04, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - R * 0.15, mouth_y), QPointF(cx + R * 0.15, mouth_y))
            # zzz
            f = QFont()
            f.setPixelSize(int(R * 0.22))
            p.setFont(f)
            for i in range(3):
                a = int(120 - 35 * i + 60 * math.sin(t * 1.5 + i))
                p.setPen(_rgb(c, max(30, min(255, a))))
                zx = cx + R * 0.5 + i * R * 0.16
                zy = cy - R * 0.6 - i * R * 0.22 - 4 * math.sin(t * 2 + i)
                p.drawText(QPointF(zx, zy), "z")
        else:
            p.setPen(QPen(col_dim, R * 0.04, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - R * 0.18, mouth_y), QPointF(cx + R * 0.18, mouth_y))

        # --- waveform внизу при listening/speaking ---
        if state in ("listening", "speaking"):
            bars = 26
            span = min(w * 0.8, 420)
            x0 = cx - span / 2
            base_y = h - 16
            p.setPen(Qt.NoPen)
            for i in range(bars):
                x = x0 + span * i / (bars - 1)
                amp = (math.sin(t * 6 + i * 0.9) * 0.5 + 0.5) * \
                      (math.sin(t * 2.3 + i * 0.37) * 0.5 + 0.5)
                bh = 3 + amp * 14
                p.setBrush(_rgb(c, 110))
                p.drawRoundedRect(QRectF(x - 1.5, base_y - bh / 2, 3, bh), 1.5, 1.5)
