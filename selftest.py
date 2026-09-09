#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Самопроверка JARVIS: окружение + логика без микрофона и окна.

Запуск:  python selftest.py
"""
import queue
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, WARN, FAIL = "✅", "🟡", "❌"
results = []


def report(name, ok, note=""):
    mark = OK if ok else WARN
    results.append(ok)
    print(f"  {mark} {name}" + (f" — {note}" if note else ""))


def check_environment():
    print("\n[1] Окружение (зависимости)")
    for module, pip_name, needed in (
            ("requests", "requests", True),
            ("speech_recognition", "SpeechRecognition", True),
            ("pyttsx3", "pyttsx3", True),
            ("tkinter", "tkinter (пакет python3-tk / tcl)", True),
            ("pyaudio", "PyAudio", False),
            ("pyautogui", "pyautogui", False),
            ("pyperclip", "pyperclip", False),
            ("PIL", "Pillow", False),
            ("vosk", "vosk (офлайн-распознавание)", False),
    ):
        try:
            __import__(module)
            report(f"{pip_name}", True)
        except Exception as exc:
            report(f"{pip_name}", not needed,
                   f"не установлен: pip install {pip_name.split()[0]}")


def check_logic():
    print("\n[2] Логика (конфиг, мозг, команды, ИИ)")
    from jarvis.config import Config

    # --- конфиг ---
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "settings.json")
        cfg = Config(path)
        cfg.set("city", "Тест-город")
        cfg.save()
        cfg2 = Config(path)
        report("Конфиг: сохранение и загрузка", cfg2.get("city") == "Тест-город")

    from jarvis.skills.custom import CustomCommands
    from jarvis.brain import Brain
    from jarvis.ai import AIClient

    class StubVoice:
        def __init__(self):
            self.spoken = []

        def say(self, text):
            self.spoken.append(text)

    def make_brain(custom_cmds=None):
        with tempfile.TemporaryDirectory() as tmp:
            pass  # временную папку используем только для пути
        cfg = Config(os.path.join(tempfile.gettempdir(), "jarvis_selftest_settings.json"))
        cfg.set("ai_enabled", False)
        cfg.set("confirm_power", False)
        v = StubVoice()
        events = queue.Queue()
        emit = lambda kind, **kw: events.put({"kind": kind, **kw})  # noqa: E731
        brain = Brain(cfg, v, emit)
        if custom_cmds is not None:
            brain.custom = custom_cmds
        return cfg, v, events, brain

    cfg, voice, events, brain = make_brain()

    # время
    brain._process("джарвис сколько времени", "text")
    ok = any("Сейчас" in s for s in voice.spoken)
    report("Встроенный навык «сколько времени»", ok)

    # приветствие
    brain._process("привет", "text")
    ok = any("Слушаю вас" in s or "Добр" in s for s in voice.spoken)
    report("Встроенный навык «привет»", ok)

    # громкость (без pyautogui не выполнит, но распознать должна)
    n_before = len(voice.spoken)
    brain._process("сделай громче", "text")
    ok = any("громче" in s.lower() for s in voice.spoken[n_before:])
    report("Встроенный навык «сделай громче»", ok)

    # свои команды
    brain._process("открой рабочую папку", "text")
    ok = any("рабочую папку" in s.lower() for s in voice.spoken)
    report("Своя команда из data/custom_commands.json", ok)

    # подтверждение питания
    cfg.set("confirm_power", True)
    n_before = len(voice.spoken)
    brain._process("выключи компьютер", "text")
    ok = any("да" in s.lower() for s in voice.spoken[n_before:])
    brain._process("да", "text")
    report("Подтверждение выключения (да/нет)", ok)
    cfg.set("confirm_power", False)

    # отмена истории
    n_before = len(voice.spoken)
    brain._process("очисти историю", "text")
    ok = any("истор" in s.lower() for s in voice.spoken[n_before:])
    report("Сброс истории диалога", ok)

    # не распознано → подсказка
    n_before = len(voice.spoken)
    brain._process("абракадабра сюрприз", "text")
    ok = any("не распознана" in s for s in voice.spoken[n_before:])
    report("Нераспознанная команда → подсказка", ok)

    # нечёткое совпадение своих команд
    cc = CustomCommands(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "data", "custom_commands.json"))
    cmd, _ = cc.match("открой рабочую папкуу")
    report("Нечёткий поиск своих команд", cmd is not None)

    # разбор ответа ИИ с блоком действий
    reply = 'Готово, открываю.\n```jarvis\n{"say": "Открываю блокнот", "actions": ' \
            '[{"type": "open_app", "target": "notepad"}]}\n```'
    clean, actions = AIClient.parse_reply(reply)
    report("Разбор блока действий в ответе ИИ",
           clean == "Открываю блокнот" and actions and actions[0]["target"] == "notepad")

    # парсер действий из редактора GUI
    try:
        from jarvis.gui import parse_actions as pa
        acts = pa("open_url | https://example.com\nsay | Привет\nмусор без пайпа")
        ok = len(acts) == 2 and acts[0]["target"] == "https://example.com"
        report("Парсер действий из редактора команд", ok)
    except ImportError:
        report("Парсер действий из редактора команд", False, "нет tkinter")

    # нормализация слуха
    from jarvis.ear import Ear
    norm = Ear.normalize("Джарвис, ПРИВЕТ! Как дела?")
    report("Нормализация текста", norm == "джарвис привет как дела")


if __name__ == "__main__":
    print("=" * 52)
    print("  JARVIS — самопроверка")
    print("=" * 52)
    check_environment()
    try:
        check_logic()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"  {FAIL} Ошибка в тестах логики: {exc}")
        results.append(False)
    passed = sum(1 for r in results if r)
    print("\n" + "=" * 52)
    print(f"  Итог: {passed}/{len(results)} проверок пройдено")
    print("=" * 52)
    sys.exit(0 if passed == len(results) else 1)
