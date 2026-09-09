# -*- coding: utf-8 -*-
"""Глобальные горячие клавиши AURA (Ctrl+Space — push-to-talk). Опционально."""
import threading


class GlobalHotkeys:
    """Обёртка над pynput. Тихо отключается, если pynput недоступен."""

    def __init__(self, on_talk):
        self.on_talk = on_talk
        self._listener = None
        self.available = False
        try:
            from pynput import keyboard
            self.available = True
            self._kb = keyboard
        except Exception:
            return

    def start(self):
        if not self.available or self._listener is not None:
            return self.available

        def on_activate():
            try:
                self.on_talk()
            except Exception:
                pass

        try:
            self._listener = self._kb.GlobalHotKeys({"<ctrl>+<space>": on_activate})
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:
            self._listener = None
            return False

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
