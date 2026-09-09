# -*- coding: utf-8 -*-
"""Лицо AURA — аватар белловолосой девушки в стиле SIGNALIS.

Каждое состояние системы = своя эмоция портрета:
  idle/spawn → neutral, listening, thinking, speaking, success, error, sleep.
Эффекты: плавный кроссфейд, «дыхание» (медленный зум), покачивание при речи,
волны-сонар при слушании, цифровой глитч при ошибке, затемнение и «zzz» во сне,
CRT-сканлайны и виньетка. Если картинки не найдены — рисуем прежнее абстрактное лицо.
"""
import math
import os
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

TICK_MS = 33
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_images")

STATE_IMAGE = {
    "idle": "neutral.jpg",
    "listening": "listening.jpg",
    "thinking": "thinking.jpg",
    "speaking": "speaking.jpg",
    "success": "success.jpg",
    "error": "error.jpg",
    "alert": "error.jpg",
    "sleep": "sleep.jpg",
}
STATE_HOLD = {"success": 2.2, "error": 2.5, "alert": 2.5}
STATE_TINT = {  # лёгкая цветная вуаль поверх кадра
    "listening": (0, 225, 255, 14),
    "thinking": (185, 130, 255, 16),
    "speaking": (60, 255, 190, 12),
    "success": (80, 255, 160, 18),
    "error": (255, 70, 70, 26),
    "alert": (255, 150, 60, 22),
    "sleep": (40, 60, 110, 60),
    "idle": None,
}


class FaceImageWidget(QWidget):
    """Аватар с эффектами. Тот же API, что у FaceWidget."""

    @classmethod
    def images_available(cls) -> bool:
        return all(os.path.exists(os.path.join(IMAGES_DIR, f))
                   for f in set(STATE_IMAGE.values()))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self._state = "idle"
        self._prev_state = "idle"
        self._pixmaps = {}
        self._fade = 1.0            # кроссфейд 0..1 к новому состоянию
        self._hold_until = 0.0
        self._resume = "idle"
        self._mood_tint = None
        self._energy = 87
        self._glitch_seed = 0
        self._scanlines = None
        self._scan_size = None
        self._has_images = self._load_images()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    # ------------------------------------------------------------------
    def _load_images(self) -> bool:
        for key, fname in STATE_IMAGE.items():
            path = os.path.join(IMAGES_DIR, fname)
            img = QImage(path)
            if img.isNull():
                self._pixmaps = {}
                return False
            self._pixmaps["error" if key == "alert" else key] = QPixmap.fromImage(img)
        return True

    @property
    def has_images(self):
        return bool(self._has_images)

    # ------------------------------------------------------------------
    def set_state(self, name: str):
        if name not in STATE_IMAGE:
            return
        now = time.time()
        if self._state in STATE_HOLD and now < self._hold_until and name in (
                "idle", "listening"):
            self._resume = name
            return
        if name != self._state:
            self._prev_state = self._state
            self._fade = 0.0
            if name in ("error", "alert"):
                self._glitch_seed = random.random() * 100
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
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            self._draw_avatar(p)
        finally:
            p.end()

    # ------------------------------------------------------------------
    def _draw_avatar(self, p: QPainter):
        t = time.time()
        w, h = self.width(), self.height()
        state = self._state

        if self._state in STATE_HOLD and t > self._hold_until:
            self._state = self._resume or "idle"

        # кроссфейд
        self._fade = min(1.0, self._fade + 0.09)

        p.fillRect(0, 0, w, h, QColor("#0a0f1c"))

        # --- «дыхание» камеры ---
        breath = 1.014 + 0.014 * math.sin(t * 1.05)
        dy = 0.0
        if state == "speaking":
            dy = 3.0 * math.sin(t * 7.3) + 1.6 * math.sin(t * 11.7)
        elif state == "listening":
            dy = 1.2 * math.sin(t * 2.2)
        elif state == "sleep":
            dy = 2.0 * math.sin(t * 0.8)

        base = self._pixmaps.get("error" if state == "alert" else state)
        prev = self._pixmaps.get(self._prev_state)

        def draw_pixmap(pix, opacity):
            if pix is None or pix.isNull():
                return
            pw, ph = pix.width(), pix.height()
            scale = max(w / pw, h / ph) * breath
            dw, dh = pw * scale, ph * scale
            dx = (w - dw) / 2
            dyy = (h - dh) / 2 + dy
            p.setOpacity(opacity)
            p.drawPixmap(QRectF(dx, dyy, dw, dh).toRect(), pix)

        # уходящее состояние (при кроссфейде)
        if self._fade < 1.0 and prev is not None:
            draw_pixmap(prev, 1.0)
        draw_pixmap(base, self._fade)
        p.setOpacity(1.0)

        # --- цветная вуаль состояния ---
        tint = STATE_TINT.get(state)
        if tint:
            p.fillRect(0, 0, w, h, QColor(*tint))
        # настроение подмешиваем в покое
        if self._mood_tint and state in ("idle", "sleep"):
            r, g, b = self._mood_tint
            p.fillRect(0, 0, w, h, QColor(r, g, b, 16))

        # --- эффекты состояний ---
        if state == "listening":
            self._draw_wave(p, w, h, t, (0, 225, 255))
        elif state == "speaking":
            self._draw_wave(p, w, h, t, (60, 255, 190))
        elif state in ("error", "alert"):
            self._draw_glitch(p, w, h, t)
        elif state == "thinking":
            self._draw_orbit(p, w, h, t)
        elif state == "sleep":
            self._draw_zzz(p, w, h, t)

        # --- CRT-сканлайны и виньетка ---
        self._draw_crt(p, w, h)

    # ------------------------------------------------------------------
    def _draw_wave(self, p: QPainter, w, h, t, rgb):
        bars, span = 26, min(w * 0.78, 300)
        x0 = (w - span) / 2
        base_y = h - 14
        p.setPen(Qt.NoPen)
        for i in range(bars):
            x = x0 + span * i / (bars - 1)
            amp = (math.sin(t * 6 + i * 0.9) * 0.5 + 0.5) * \
                  (math.sin(t * 2.3 + i * 0.37) * 0.5 + 0.5)
            bh = 3 + amp * 13
            p.setBrush(QColor(*rgb, 130))
            p.drawRoundedRect(QRectF(x - 1.5, base_y - bh / 2, 3, bh), 1.5, 1.5)

    def _draw_glitch(self, p: QPainter, w, h, t):
        """Цифровой глитч: рваные горизонтальные полосы + вспышки."""
        rnd = random.Random(self._glitch_seed + int(t * 8))
        base = self._pixmaps.get("error")
        if base is None:
            return
        for _ in range(7):
            if rnd.random() < 0.6:
                y = rnd.randint(0, max(1, h - 12))
                bh = rnd.randint(4, 16)
                dx = rnd.randint(-16, 16)
                p.drawPixmap(QRectF(dx, y, w, bh).toRect(), base,
                             QRectF(0, y * base.height() / h, base.width(),
                                    bh * base.height() / h).toRect())
        if rnd.random() < 0.5:
            p.fillRect(0, 0, w, h, QColor(255, 60, 60, 18))
        # красная рамка-предупреждение
        pen = QPen(QColor(255, 80, 80, 130), 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(6, 6, w - 12, h - 12), 10, 10)

    def _draw_orbit(self, p: QPainter, w, h, t):
        cx, cy = w / 2, h * 0.42
        R = min(w, h) * 0.44
        p.setPen(Qt.NoPen)
        for i in range(3):
            ang = t * 1.7 + i * 2.09
            dx = cx + R * math.cos(ang)
            dy = cy + R * 0.92 * math.sin(ang) * 0.35
            p.setBrush(QColor(185, 130, 255, 190))
            p.drawEllipse(QPointF(dx, dy), 3.2, 3.2)

    def _draw_zzz(self, p: QPainter, w, h, t):
        f = QFont()
        f.setPixelSize(max(14, int(h * 0.06)))
        p.setFont(f)
        for i in range(3):
            a = int(150 - 40 * i + 60 * math.sin(t * 1.5 + i))
            p.setPen(QColor(150, 180, 255, max(40, min(230, a))))
            zx = w * 0.78 + i * w * 0.045
            zy = h * 0.22 - i * h * 0.07 - 4 * math.sin(t * 2 + i)
            p.drawText(QPointF(zx, zy), "z" * (i + 1))

    def _draw_crt(self, p: QPainter, w, h):
        # кэш сканлайнов на размер
        if self._scan_size != (w, h):
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setPen(Qt.NoPen)
            for y in range(0, h, 3):
                q.setBrush(QColor(0, 0, 0, 14))
                q.drawRect(0, y, w, 1)
            q.end()
            self._scanlines = pm
            self._scan_size = (w, h)
        p.drawPixmap(0, 0, self._scanlines)
        grad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.75)
        grad.setColorAt(0.62, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRect(0, 0, w, h)
