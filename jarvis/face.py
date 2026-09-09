# -*- coding: utf-8 -*-
"""Лицо Джарвиса: анимированный HUD на Tkinter Canvas.

Состояния (меняются по действиям ассистента):
  idle      — спокойное свечение, «дышит»
  listening — глаза шире, вокруг расходятся волны
  thinking  — щурится, вокруг вращаются дуги и спутники
  speaking  — анимированный рот-эквалайзер
  alert     — красный пульс (ошибка/внимание)
  off       — потушен
"""
import math
import time
import tkinter as tk

TICK_MS = 33  # ~30 fps

PALETTE = {
    "idle":      (70, 150, 255),
    "listening": (0, 225, 255),
    "thinking":  (185, 130, 255),
    "speaking":  (60, 255, 190),
    "alert":     (255, 90, 90),
    "off":       (60, 75, 95),
}

EYE_H = {"idle": 0.30, "listening": 0.46, "thinking": 0.16, "speaking": 0.30,
         "alert": 0.40, "off": 0.22}


def _lerp(a, b, k):
    return a + (b - a) * k


def _rgb(c):
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


class FaceCanvas(tk.Canvas):
    def __init__(self, master, state="idle", **kw):
        super().__init__(master, bg="#0a0f1c", highlightthickness=0, **kw)
        self._state = state
        self._color = list(PALETTE[state])
        self._phase = 0.0        # угол вращения дуг
        self._ripple = 0.0       # волны при слушании
        self._alert_until = 0.0
        self._prev = "idle"
        self._running = True
        self._geom = None

        # элементы создаются один раз, дальше только обновляем
        self._halo = self.create_oval(0, 0, 1, 1, outline="", width=2)
        self._ring = self.create_arc(0, 0, 1, 1, start=0, extent=270,
                                     style="arc", width=5, outline="")
        self._ring2 = self.create_arc(0, 0, 1, 1, start=180, extent=120,
                                      style="arc", width=2, outline="")
        self._core = self.create_oval(0, 0, 1, 1, fill="", outline="")
        self._eye_l = self.create_oval(0, 0, 1, 1, fill="", outline="")
        self._eye_r = self.create_oval(0, 0, 1, 1, fill="", outline="")
        self._mouth_bars = [self.create_rectangle(0, 0, 1, 1, fill="", outline="", width=0)
                            for _ in range(14)]
        self._ripples = [self.create_oval(0, 0, 1, 1, outline="", width=2)
                         for _ in range(3)]
        self._dots = [self.create_oval(0, 0, 1, 1, fill="", outline="") for _ in range(3)]

        self.bind("<Configure>", lambda e: setattr(self, "_geom", None))
        self.after(TICK_MS, self._tick)

    # ------------------------------------------------------------------
    def set_state(self, name: str):
        if name == "alert":
            self._alert_until = time.time() + 2.5
            self._state = "alert"
            return
        if name in PALETTE:
            if self._state == "alert" and time.time() < self._alert_until and name != "off":
                self._prev = name          # вернёмся после тревоги
                return
            self._state = name

    def current_state(self):
        return self._state

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    def _layout(self):
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        cx, cy = w / 2, h / 2
        R = min(w, h) * 0.36
        return w, h, cx, cy, R

    def _tick(self):
        if not self._running:
            return
        try:
            self._draw()
        except tk.TclError:
            self._running = False
            return
        self.after(TICK_MS, self._tick)

    def _draw(self):
        t = time.time()
        # восстановление после тревоги
        if self._state == "alert" and t > self._alert_until:
            self._state = self._prev or "idle"
        state = self._state
        target = PALETTE[state]
        self._color = [_lerp(c, tg, 0.18) for c, tg in zip(self._color, target)]
        col = _rgb([int(c) for c in self._color])
        col_dim = _rgb([int(c * 0.45) for c in self._color])
        col_deep = _rgb([int(c * 0.16) for c in self._color])

        w, h, cx, cy, R = self._layout()
        breath = 1 + 0.02 * math.sin(t * 1.8)          # спокойное «дыхание»
        pulse = 0.5 + 0.5 * math.sin(t * 4.0)
        R_eff = R * breath
        active = state != "off"

        # --- внешнее свечение-ореол ---
        r1 = R_eff * (1.16 + 0.03 * pulse)
        self.coords(self._halo, cx - r1, cy - r1, cx + r1, cy + r1)
        self.itemconfig(self._halo, outline=col_dim if active else "")

        # --- вращающиеся дуги (быстрее в thinking) ---
        speed = {"thinking": 2.6, "listening": 1.2, "speaking": 0.9}.get(state, 0.35)
        self._phase += speed * TICK_MS / 1000 * math.pi
        rr = R_eff * 1.05
        self.coords(self._ring, cx - rr, cy - rr, cx + rr, cy + rr)
        self.itemconfig(self._ring, start=self._phase * 57.3 % 360,
                        outline=col if active else col_dim)
        rr2 = R_eff * 1.28
        self.coords(self._ring2, cx - rr2, cy - rr2, cx + rr2, cy + rr2)
        self.itemconfig(self._ring2, start=(-self._phase * 1.6) * 57.3 % 360,
                        outline=col_dim if active else col_deep)

        # --- ядро ---
        rc = R_eff * 0.62 * (1 + 0.05 * pulse if state == "speaking" else 1)
        self.coords(self._core, cx - rc, cy - rc * 1.05, cx + rc, cy + rc * 1.05)
        self.itemconfig(self._core, fill=col_deep if active else "#0d1524",
                        outline=col_dim if active else "#1a2333")

        # --- глаза ---
        eh = R * EYE_H.get(state, 0.3)
        ew = R * 0.20
        gap = R * 0.30
        eye_y = cy - R * 0.18
        glow = 1 + 0.12 * pulse if state in ("listening", "alert", "speaking") else 1
        for item, sx in ((self._eye_l, -1), (self._eye_r, 1)):
            ex = cx + sx * gap
            self.coords(item, ex - ew, eye_y - eh * glow, ex + ew, eye_y + eh * glow)
            self.itemconfig(item, fill=col if active else col_dim, outline="")

        # --- рот ---
        bars = self._mouth_bars
        n = len(bars)
        mouth_y = cy + R * 0.34
        base_h = R * 0.22
        bw = R * 0.055
        span = R * 0.78
        if state == "speaking":
            for i, item in enumerate(bars):
                x = cx - span / 2 + (span / (n - 1)) * i
                wob = abs(math.sin(t * 9 + i * 1.7)) * (0.35 + 0.65 * abs(math.sin(t * 3.1 + i)))
                bh = base_h * (0.18 + 0.82 * wob)
                self.coords(item, x - bw / 2, mouth_y - bh, x + bw / 2, mouth_y + bh)
                self.itemconfig(item, fill=col, outline="")
        elif state in ("idle", "thinking", "listening"):
            line_h = R * 0.02
            for i, item in enumerate(bars):
                if i == n // 2:
                    x = cx
                    self.coords(item, x - span / 2, mouth_y - line_h, x + span / 2, mouth_y + line_h)
                    self.itemconfig(item, fill=col_dim, outline="")
                else:
                    self.coords(item, 0, 0, 0, 0)
                    self.itemconfig(item, fill="", outline="")
        else:
            for item in bars:
                self.coords(item, 0, 0, 0, 0)
                self.itemconfig(item, fill="", outline="")

        # --- волны при слушании ---
        if state == "listening":
            self._ripple = (self._ripple + 0.02) % 1.0
            for i, item in enumerate(self._ripples):
                k = (self._ripple + i / len(self._ripples)) % 1.0
                rw = R_eff * (1.1 + k * 0.9)
                fade = int((1 - k) * 255)
                rc_ = tuple(int(c * fade / 255 * 0.9) for c in PALETTE["listening"])
                self.coords(item, cx - rw, cy - rw, cx + rw, cy + rw)
                self.itemconfig(item, outline=_rgb(rc_) if fade > 40 else "#0a0f1c")
        else:
            for item in self._ripples:
                self.coords(item, 0, 0, 0, 0)

        # --- спутники при thinking ---
        if state == "thinking":
            for i, item in enumerate(self._dots):
                ang = self._phase * 1.3 + i * 2.09
                dist = R_eff * 1.18
                dx = cx + dist * math.cos(ang)
                dy = cy + dist * math.sin(ang)
                sz = R * 0.045
                self.coords(item, dx - sz, dy - sz, dx + sz, dy + sz)
                self.itemconfig(item, fill=col, outline="")
        else:
            for item in self._dots:
                self.coords(item, 0, 0, 0, 0)
