# -*- coding: utf-8 -*-
"""Teach Mode: AURA записывает ваши действия и превращает их в команду.

Запись: клики мышью → click x,y; текст → type_text; Enter/Esc/Tab/F-клавиши → press.
Паузы > 1.5 сек превращаются в wait. Требуется pynput (опционально).
"""
import threading
import time

try:
    from pynput import mouse, keyboard
    PYNPUT_OK = True
except Exception:  # pragma: no cover
    PYNPUT_OK = False

SPECIAL_KEYS = {
    "enter": "enter", "space": "space", "tab": "tab", "esc": "esc",
    "backspace": "backspace", "delete": "delete", "home": "home", "end": "end",
    "up": "up", "down": "down", "left": "left", "right": "right",
}


class MacroRecorder:
    def __init__(self, emit=None):
        self.emit = emit or (lambda *a, **k: None)
        self.recording = False
        self._events = []            # (time, kind, payload)
        self._buffer = []            # накопленный печатаемый текст
        self._lock = threading.Lock()
        self._m_listener = None
        self._k_listener = None
        self._pressed_mods = set()

    # ---------- публичное ----------
    @property
    def available(self):
        return PYNPUT_OK

    def start(self) -> bool:
        if not PYNPUT_OK or self.recording:
            return False
        with self._lock:
            self._events = []
            self._buffer = []
            self.recording = True

        def on_click(x, y, button, pressed):
            if pressed and self.recording and str(button) == "Button.left":
                self._flush_text()
                with self._lock:
                    self._events.append((time.time(), "click", f"{int(x)},{int(y)}"))

        def on_press(key):
            if not self.recording:
                return
            try:
                name = key.char
                if name and name.isprintable():
                    if self._pressed_mods & {"ctrl", "alt"}:
                        self._flush_text()
                        mods = "+".join(sorted(self._pressed_mods | {"ctrl"}))
                        with self._lock:
                            self._events.append(
                                (time.time(), "press", f"{mods}+{name.lower()}"))
                    else:
                        with self._lock:
                            self._buffer.append(name)
                    return
            except AttributeError:
                pass
            kname = getattr(key, "name", "") or ""
            if kname in ("ctrl_l", "ctrl_r", "alt_l", "alt_r", "alt_gr"):
                self._pressed_mods.add({"ctrl_l": "ctrl", "ctrl_r": "ctrl",
                                        "alt_l": "alt", "alt_r": "alt",
                                        "alt_gr": "ctrl"}.get(kname, kname))
                return
            if kname == "shift" or kname in ("shift_l", "shift_r"):
                return
            self._flush_text()
            if kname in SPECIAL_KEYS:
                with self._lock:
                    self._events.append((time.time(), "press", SPECIAL_KEYS[kname]))
            elif kname.startswith("f") and kname[1:].isdigit():
                with self._lock:
                    self._events.append((time.time(), "press", kname))

        def on_release(key):
            kname = getattr(key, "name", "") or ""
            if kname in ("ctrl_l", "ctrl_r"):
                self._pressed_mods.discard("ctrl")
            elif kname in ("alt_l", "alt_r", "alt_gr"):
                self._pressed_mods.discard("alt")

        try:
            self._m_listener = mouse.Listener(on_click=on_click)
            self._k_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._m_listener.daemon = True
            self._k_listener.daemon = True
            self._m_listener.start()
            self._k_listener.start()
        except Exception as exc:
            self.recording = False
            self.emit("log", level="error", msg=f"Запись не запустилась: {exc}")
            return False
        self.emit("log", level="system",
                  msg="⏺ Запись действий началась. Делайте свои действия, затем нажмите «Стоп».")
        return True

    def stop(self):
        """Остановить запись и вернуть список действий."""
        if not self.recording:
            return []
        self.recording = False
        self._flush_text()
        for lst in (self._m_listener, self._k_listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._m_listener = self._k_listener = None
        actions, stats = self._build_actions()
        dropped = stats["raw"] - stats["clean"]
        self.emit("log", level="system",
                  msg=f"⏹ Запись остановлена: {stats['raw']} сырых событий → "
                      f"{stats['clean']} действий"
                      + (f" (убрано лишних: {dropped})" if dropped > 0 else ""))
        return actions

    # ---------- внутреннее ----------
    def _flush_text(self):
        with self._lock:
            if self._buffer:
                text = "".join(self._buffer)
                self._buffer = []
                if text.strip():
                    self._events.append((time.time(), "type_text", text))

    MIN_CLICK_INTERVAL = 0.3     # случайные двойные клики склеиваем
    MIN_WAIT = 0.5               # паузы короче — мусор
    MAX_WAIT = 10                # длинные паузы ограничиваем

    def _build_actions(self):
        """Сырые события → чистая цепочка действий.

        Очистка: склейка повторных кликов, слияние печати, нормализация пауз.
        Возвращает (действия, статистика dict).
        """
        with self._lock:
            events = list(self._events)
            self._events = []
        raw_count = len(events)
        cleaned = []
        last_click = 0.0
        prev_t = None
        for t, kind, payload in events:
            if kind == "click":
                # дребезг: клики чаще 0.3 сек в той же точке — игнор
                if t - last_click < self.MIN_CLICK_INTERVAL and cleaned and \
                        cleaned[-1].get("target") == payload:
                    prev_t = t
                    continue
                last_click = t
                if prev_t is not None and t - prev_t >= self.MIN_WAIT:
                    cleaned.append({"type": "wait",
                                    "target": str(min(self.MAX_WAIT,
                                                      round(t - prev_t, 1)))})
                cleaned.append({"type": "click", "target": payload})
            elif kind == "press":
                if prev_t is not None and t - prev_t >= self.MIN_WAIT:
                    cleaned.append({"type": "wait",
                                    "target": str(min(self.MAX_WAIT,
                                                      round(t - prev_t, 1)))})
                cleaned.append({"type": "press", "target": payload})
            else:  # type_text — склеиваем подряд идущую печать
                if cleaned and cleaned[-1].get("type") == "type_text":
                    cleaned[-1]["target"] = (cleaned[-1].get("target", "") +
                                             payload)
                else:
                    if prev_t is not None and t - prev_t >= self.MIN_WAIT:
                        cleaned.append({"type": "wait",
                                        "target": str(min(self.MAX_WAIT,
                                                          round(t - prev_t, 1)))})
                    cleaned.append({"type": "type_text", "target": payload})
            prev_t = t
        stats = {"raw": raw_count, "clean": len(cleaned)}
        return cleaned, stats
