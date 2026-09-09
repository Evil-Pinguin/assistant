#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""J.A.R.V.I.S. — голосовой ассистент с лицом и ИИ. Точка входа.

Запуск:  python main.py
Если tkinter не установлен — запустится консольный режим (без лица).
"""
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis.config import Config, DATA_DIR, LOG_FILE   # noqa: E402


def make_logger():
    import logging
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])
    return logging.getLogger("jarvis")


def main():
    log = make_logger()
    config = Config()

    events: "queue.Queue[dict]" = queue.Queue()

    def emit(kind, **data):
        events.put({"kind": kind, **data})

    # --- компоненты ---
    from jarvis.voice import Voice
    from jarvis.ear import Ear
    from jarvis.brain import Brain

    voice = Voice(config, emit)
    ear = Ear(config, emit, on_text=lambda text, src: brain.handle(text, src))
    brain = Brain(config, voice, emit, ear=ear)

    def drain_console():
        """Печать событий в консоль (для CLI-режима и отладки)."""
        while True:
            try:
                evt = events.get(timeout=0.1)
            except queue.Empty:
                continue
            kind = evt.get("kind")
            if kind == "log":
                icon = {"user": "🗣", "jarvis": "🤖", "error": "❌"}.get(
                    evt.get("level"), "•")
                print(f"{icon} {evt.get('msg', '')}")

    # --- GUI или консоль ---
    try:
        import tkinter  # noqa: F401
        from jarvis.gui import JarvisApp
    except ImportError as exc:
        print("=" * 60)
        print(f"tkinter недоступен ({exc}) — запускаю консольный режим.")
        print("Печатайте команды. Для выхода: exit")
        print("=" * 60)
        import threading
        threading.Thread(target=drain_console, daemon=True).start()
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
        return

    app = JarvisApp(config, voice, ear, brain, events)
    log.info("JARVIS запущен")
    try:
        app.mainloop()
    finally:
        ear.stop()
        voice.shutdown()
        log.info("JARVIS остановлен")


if __name__ == "__main__":
    main()
