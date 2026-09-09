# -*- coding: utf-8 -*-
"""Глобальные горячие клавиши AURA.

По умолчанию:
  Ctrl+Space — разовое прослушивание (push-to-talk)
  Ctrl+1..4  — быстрые запуски (настраиваются в data/settings.json → hotkeys)

Требуется pynput; если его нет — тихо отключается.
"""
import threading


class GlobalHotkeys:
    """Обёртка над pynput. Тихо отключается, если pynput недоступен."""

    DEFAULT_HOTKEYS = {
        "ctrl+1": "dev",
        "ctrl+2": "krita",
        "ctrl+3": "unity",
        "ctrl+4": "blender",
    }

    def __init__(self, on_talk, get_actions=None):
        """get_actions() -> {"ctrl+1": callable, ...} — пользовательские запуски."""
        self.on_talk = on_talk
        self.get_actions = get_actions or (lambda: {})
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
        try:
            self._listener = self._kb.GlobalHotKeys(self._build_map())
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:
            self._listener = None
            return False

    def _build_map(self):
        combo_map = {"<ctrl>+<space>": self.on_talk}
        for combo, action in self.get_actions().items():
            combo_map[self._to_pynput(combo)] = action
        return combo_map

    @staticmethod
    def _to_pynput(combo: str) -> str:
        """'ctrl+1' -> '<ctrl>+<1>'; 'ctrl+shift+v' -> '<ctrl>+<shift>+<v>'."""
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        wrapped = [f"<{p}>" for p in parts]
        return "+".join(wrapped)

    def restart(self):
        """Перечитать хоткеи (после изменения настроек)."""
        self.stop()
        return self.start()

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
