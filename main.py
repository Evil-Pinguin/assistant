#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AURA — персональный ИИ-ассистент. Точка входа.

Запуск:  python main.py
Без PySide6 запустится консольный режим (без лица).
"""
import logging
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aura.config import Config, DATA_DIR, LOG_FILE  # noqa: E402


def make_logger():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])
    return logging.getLogger("aura")


def build_core(config, events):
    """Создать общие компоненты (используются и GUI, и консолью)."""
    from aura.voice import Voice
    from aura.ear import Ear
    from aura.brain import Brain
    from aura.plugins import load_plugins

    def emit(kind, **data):
        events.put({"kind": kind, **data})

    voice = Voice(config, emit)
    brain = Brain(config, voice, emit)
    ear = Ear(config, emit, on_text=lambda text, src: brain.handle(text, src))
    load_plugins(brain)
    return emit, voice, ear, brain


def run_console(config):
    events = queue.Queue()
    emit, voice, ear, brain = build_core(config, events)
    print("=" * 62)
    print("  AURA · Аврора — консольный режим (нет PySide6)")
    print("  Печатайте команды. Для выхода: exit")
    print("=" * 62)

    def drain():
        while True:
            try:
                evt = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if evt.get("kind") == "log":
                icon = {"user": "🗣", "aura": "💠", "error": "❌"}.get(
                    evt.get("level"), "•")
                print(f"{icon} {evt.get('msg', '')}")

    import threading
    threading.Thread(target=drain, daemon=True).start()
    try:
        while True:
            text = input("Вы> ").strip()
            if text.lower() in ("exit", "quit", "выход"):
                break
            if text:
                brain.handle(text, "text")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        ear.stop()
        voice.shutdown()


def run_gui(config, log):
    from PySide6.QtWidgets import QApplication
    from aura.gui import MainWindow
    from aura.hotkey import GlobalHotkeys
    from aura.teach import MacroRecorder

    app = QApplication(sys.argv)
    app.setApplicationName("AURA")
    events = queue.Queue()
    emit, voice, ear, brain = build_core(config, events)

    hotkeys = GlobalHotkeys(on_talk=lambda: ear.listen_once())
    if config.get("hotkey_enabled", True) and hotkeys.available:
        if hotkeys.start():
            log.info("Глобальная клавиша Ctrl+Space активна")
    elif not hotkeys.available:
        log.info("pynput не установлен — глобальные клавиши отключены "
                 "(pip install pynput)")

    recorder = MacroRecorder(emit=emit)
    win = MainWindow(config, voice, ear, brain, events,
                     hotkeys=hotkeys, recorder=recorder)
    win.show()
    log.info("AURA запущена")
    code = app.exec()
    ear.stop()
    voice.shutdown()
    return code


def main():
    log = make_logger()
    config = Config()
    try:
        import PySide6  # noqa: F401
        return run_gui(config, log)
    except ImportError:
        run_console(config)
        return 0


if __name__ == "__main__":
    sys.exit(main())
