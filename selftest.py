#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Самопроверка AURA: зависимости, логика ядра, UI-дым (если есть PySide6).

Запуск:  python selftest.py
"""
import os
import queue
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []


def report(name, ok, note=""):
    mark = "✅" if ok else "🟡"
    results.append(ok)
    print(f"  {mark} {name}" + (f" — {note}" if note else ""))


def check_environment():
    print("\n[1] Зависимости")
    for module, pip_name, needed in (
            ("PySide6", "PySide6 (интерфейс)", True),
            ("requests", "requests", True),
            ("speech_recognition", "SpeechRecognition", True),
            ("pyttsx3", "pyttsx3 (озвучка)", True),
            ("psutil", "psutil (статистика, закрытие приложений)", True),
            ("pyaudio", "PyAudio (микрофон)", False),
            ("pyautogui", "pyautogui (автоматизация)", False),
            ("pyperclip", "pyperclip", False),
            ("PIL", "Pillow (скриншоты, зрение)", False),
            ("pynput", "pynput (горячие клавиши, Teach Mode)", False),
            ("vosk", "vosk (офлайн-распознавание)", False),
    ):
        try:
            __import__(module)
            report(pip_name, True)
        except Exception:
            report(pip_name, not needed, f"не установлен: pip install {pip_name.split()[0]}")


class StubVoice:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)

    def available_voices(self):
        return []

    def shutdown(self):
        pass


def make_brain(tmpdir):
    from aura.config import Config
    from aura.brain import Brain
    cfg = Config(os.path.join(tmpdir, "settings.json"))
    cfg.set("ai_enabled", False)
    cfg.set("confirm_power", False)
    cfg.set("permission_level", "god")   # в тестах разрешаем всё
    cfg.set("city", "Тест-сити")
    v = StubVoice()
    events = queue.Queue()
    brain = Brain(cfg, v, lambda kind, **kw: events.put({"kind": kind, **kw}))
    return cfg, v, events, brain


def check_logic():
    print("\n[2] Ядро (конфиг, память, разрешения, режимы, мозг)")
    from aura.config import Config
    from aura.memory import Memory
    from aura.permissions import Permissions, LEVELS
    from aura.profiles import Profiles, BUILTIN_PROFILES
    from aura.activity import Activity
    from aura.mood import MoodEngine
    from aura.skills.custom import CustomCommands
    from aura.ai import AIClient
    from aura.skills import actions as A

    # конфиг
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.json")
        cfg = Config(p)
        cfg.set("city", "Тест")
        cfg.save()
        report("Конфиг: сохранение/загрузка", Config(p).get("city") == "Тест")

    # память
    with tempfile.TemporaryDirectory() as tmp:
        mem = Memory(os.path.join(tmp, "m.json"))
        mem.set_pref("projects_folder", "D:/Projects")
        mem.add_fact("работаю над Аурой")
        mem2 = Memory(os.path.join(tmp, "m.json"))
        report("Память: предпочтения и факты",
               mem2.get_pref("projects_folder") == "D:/Projects"
               and mem2.facts == ["работаю над Аурой"]
               and "D:/Projects" in mem2.as_prompt())

    # разрешения
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(os.path.join(tmp, "s.json"))
        perms = Permissions(cfg)
        cfg.set("permission_level", "safe")
        report("Разрешения: SAFE запрещает shell", perms.gate("shell") == "deny")
        cfg.set("permission_level", "normal")
        report("Разрешения: NORMAL спрашивает shell", perms.gate("shell") == "confirm")
        perms.set_override("shell", "allow")
        report("Разрешения: переопределение", perms.gate("shell") == "allow")
        cfg.set("permission_level", "god")
        report("Разрешения: GOD разрешает всё", perms.gate("files_delete") == "allow")
        acts = [{"type": "shell", "target": "x"}, {"type": "say", "text": "hi"}]
        cfg.set("permission_level", "safe")
        cfg.set("perm_overrides", {})
        report("Разрешения: strip_denied убирает запрещённое",
               A.strip_denied(acts, perms) == ([acts[1]], ["shell"]))

    # режимы
    with tempfile.TemporaryDirectory() as tmp:
        profs = Profiles(os.path.join(tmp, "p.json"))
        report("Режимы: встроенные загружены", len(profs.all()) >= 5)
        p = profs.match("включи игровой режим")
        report("Режимы: «включи игровой режим» найден", p and p["name"] == "Игры")
        profs.upsert({"name": "Тест", "phrases": ["тест режим"], "actions": [
            {"type": "say", "text": "ок"}]})
        report("Режимы: сохранение пользовательского",
              Profiles(os.path.join(tmp, "p.json")).match("тест режим") is not None)

    # активность/undo
    act = Activity()
    calls = []
    act.add("тест", undo=lambda: calls.append(1))
    act.add("неотменяемое")
    report("Активность: undo пропускает неотменяемое",
           act.undo_last() == "тест" and calls)

    # настроение
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(os.path.join(tmp, "s.json"))
        mood = MoodEngine(cfg, lambda *a, **k: None)
        report("Настроение: фрустрация ловится",
               mood.observe_user("опять этот код сломался")
               and mood.state()["mood"] == "concerned")
        mood.mood = "neutral"
        mood.on_success()
        report("Настроение: успех → уверенность", mood.state()["mood"] == "confident")

    # мозг: команды
    with tempfile.TemporaryDirectory() as tmp:
        cfg, voice, events, brain = make_brain(tmp)
        brain._process("джарвис сколько времени", "text")  # старое кодовое тоже поймает время
        brain._process("который час", "text")
        report("Мозг: «который час»", any("Сейчас" in s for s in voice.spoken))

        brain._process("привет", "text")
        report("Мозг: приветствие", any("Слушаю" in s for s in voice.spoken))

        n = len(voice.spoken)
        brain._process("сделай громче", "text")
        report("Мозг: громкость", any("громче" in s.lower() or "пакет" in s.lower()
                                      for s in voice.spoken[n:]))

        n = len(voice.spoken)
        brain._process("статус системы", "text")
        report("Мозг: статус системы", any("Процессор" in s for s in voice.spoken[n:])
               or any("psutil" in s for s in voice.spoken[n:]))

        n = len(voice.spoken)
        brain._process("запомни: я работаю над проектом Аура", "text")
        brain._process("что ты помнишь", "text")
        report("Мозг: память запомнить/вспомнить",
               any("Аура" in s or "аура" in s.lower() for s in voice.spoken[n:]))

        n = len(voice.spoken)
        brain._process("подбрось монетку", "text")
        report("Мозг: монетка", any(("Орёл" in s or "Решка" in s)
                                    for s in voice.spoken[n:]))

        # режимы через мозг
        n = len(voice.spoken)
        brain._process("ночной режим", "text")
        report("Мозг: активация режима «Ночь»",
               any("ночной" in s.lower() or "Спокойной" in s for s in voice.spoken[n:]))

        # своя команда
        n = len(voice.spoken)
        brain._process("рабочая папка", "text")
        report("Мозг: своя команда из json",
               any("рабоч" in s.lower() for s in voice.spoken[n:]))

        # подтверждение
        cfg.set("confirm_power", True)
        n = len(voice.spoken)
        brain._process("выключи компьютер", "text")
        ok = any("да" in s.lower() for s in voice.spoken[n:])
        brain._process("да", "text")
        report("Мозг: подтверждение питания", ok)

        # отмена действия
        n = len(voice.spoken)
        brain.activity.add("Открыт сайт", undo=lambda: None)
        brain._process("отмени последнее действие", "text")
        report("Мозг: «отмени последнее действие»",
               any("Отменила" in s for s in voice.spoken[n:]))

        # нераспознанное
        n = len(voice.spoken)
        brain._process("абракадабра сюрприз", "text")
        report("Мозг: подсказка при нераспознанном",
               any("не распознана" in s for s in voice.spoken[n:]))

        # заметки (путь-заглушка: open_app упадёт, но навык сработает)
        cfg.set("notes_app", os.path.join(tmp, "заметки"))
        n = len(voice.spoken)
        brain._process("ту ду лист", "text")
        import time as _t
        _t.sleep(0.8)
        report("Мозг: «ту ду лист» открывает заметки",
               any("замет" in x.lower() for x in voice.spoken[n:]))

        # быстрый запуск
        n = len(voice.spoken)
        brain._process("запусти криту", "text")
        _t.sleep(0.8)
        report("Мозг: «запусти криту» → быстрый запуск",
               any("крит" in x.lower() for x in voice.spoken[n:]))

    # нечёткий поиск своих команд
    with tempfile.TemporaryDirectory() as tmp:
        cc = CustomCommands(os.path.join(tmp, "c.json"))
        cc.upsert({"name": "T", "phrases": ["открой ютуб"], "actions": [
            {"type": "say", "text": "ок"}]})
        report("Свои команды: нечёткое совпадение",
               cc.match("открой ютубе")[0] is not None)

    # разбор ответа ИИ
    reply = ('Готово.\n```aura\n{"say": "Открываю", "actions": '
             '[{"type": "open_app", "target": "code"}]}\n```')
    clean, actions = AIClient.parse_reply(reply)
    report("ИИ: разбор блока действий",
           clean == "Открываю" and actions and actions[0]["target"] == "code")

    # категории разрешений действий
    cats = A.collect_categories([{"type": "shell", "target": "x"},
                                 {"type": "open_url", "target": "y"}])
    report("Действия: категории разрешений", cats == {"shell", "browser_open"})

    # хоткеи: сборка карты pynput
    try:
        from aura.hotkey import GlobalHotkeys
        hk = GlobalHotkeys(on_talk=lambda: None, get_actions=lambda: {"ctrl+1": lambda: None})
        if not hk.available:
            report("Хоткеи: класс работает", True,
                   "pynput нет в песочнице — на Windows установится из requirements")
        else:
            report("Хоткеи: карта pynput строится",
                   hk._to_pynput("ctrl+1") == "<ctrl>+<1>")
    except Exception as exc:
        report("Хоткеи: класс работает", False, str(exc))

    # машина состояний
    from aura.state import StateMachine
    emitted = []
    sm = StateMachine(lambda kind, **kw: emitted.append(kw) if kind == "state" else None)
    sm.set("listening")
    sm.set("processing")
    report("Машина состояний: переходы и события",
           sm.state == "processing" and len(emitted) == 2
           and emitted[-1]["name"] == "processing" and sm.is_busy())

    # resolver
    from aura.resolver import resolve, BUILTIN_ALIASES
    report("Resolver: алиасы и поиск в системе",
           BUILTIN_ALIASES.get("браузер") == "chrome"
           and resolve("python3")[1] in ("path", "shortcut", "running", "registry"))

    # очистка записи (teach)
    from aura.teach import MacroRecorder
    rec = MacroRecorder()
    base = __import__("time").time()
    with rec._lock:
        rec._events = [
            (base + 0.0, "click", "100,200"),
            (base + 0.1, "click", "100,200"),      # дребезг — уберётся
            (base + 1.0, "type_text", "При"),
            (base + 1.2, "type_text", "вет"),      # склеится с предыдущей
            (base + 3.5, "click", "300,400"),      # пауза 2.3с → wait
            (base + 3.6, "click", "300,400"),      # дребезг — уберётся
        ]
    actions, stats = rec._build_actions()
    kinds = [a["type"] for a in actions]
    report("Очистка записи: дребезг/слияние/паузы",
           stats["raw"] == 6 and len(actions) == 5
           and "wait" in kinds
           and any(a.get("target") == "Привет" for a in actions))

    # execute_actions возвращает (ok, failed)
    with tempfile.TemporaryDirectory() as tmp:
        cfgx = Config(os.path.join(tmp, "s.json"))
        from aura.skills.actions import ActionContext, execute_actions
        ctxx = ActionContext(say=lambda x: None, log=lambda *a, **k: None, config=cfgx)
        res = execute_actions([{"type": "wait", "target": "0"},
                               {"type": "несуществует"}], ctxx)
        report("Действия: честный результат (ok, failed)", res == (1, 1))

    # VU-уровни
    from aura.ear import audio_levels
    report("VU-метр: функция уровней", len(audio_levels(None)) == 16)

    # зрение: сборка сообщений
    from aura import vision as V
    msgs = V.vision_messages("что на экране?", b"jpegdata")
    report("Зрение: сообщения с картинкой",
           "image_url" in msgs[-1]["content"][1] and msgs[-1]["content"][0]["type"] == "text")

    # ================= контекст ПК =================
    import time as _t
    from aura.context import ContextEngine, evaluate_alerts
    with tempfile.TemporaryDirectory() as tmp:
        ce = ContextEngine(config={}, journal_path=os.path.join(tmp, "j.json"))
        st = ce.system()
        report("Контекст: снимок системы (CPU/RAM/сеть)",
               isinstance(st.get("ram"), (int, float)) and 0 <= st["ram"] <= 100
               and st.get("online") in (True, False, None))
        ce.note("open", "открыто: код",
                actions=[{"type": "open_app", "target": "code"}])
        ce2 = ContextEngine(config={}, journal_path=os.path.join(tmp, "j.json"))
        report("Контекст: журнал переживает перезапуск",
               bool(ce2.recent(1)) and ce2.recent(1)[0]["desc"] == "открыто: код")

    with tempfile.TemporaryDirectory() as tmp:
        ce = ContextEngine(config={}, journal_path=os.path.join(tmp, "j.json"))
        yest = _t.time() - 86400
        ce._journal.extend([
            {"ts": yest, "kind": "workflow", "desc": "режим Работа",
             "actions": [{"type": "open_app", "target": "code"}]},
            {"ts": yest + 120, "kind": "open", "desc": "сайт: github",
             "actions": [{"type": "open_url", "target": "https://github.com"}]},
            {"ts": _t.time(), "kind": "open", "desc": "сегодняшнее",
             "actions": [{"type": "open_app", "target": "calc"}]},
        ])
        s = ce.find_past_session()
        report("Контекст: «как вчера» находит прошлую сессию",
               s is not None and len(s["steps"]) == 2
               and s["steps"][0]["desc"] == "режим Работа")

    codes, _ = evaluate_alerts({"ram": 95, "cpu": 10, "disk_free_pct": 50,
                                "online": True}, 0, True)
    codes2, _ = evaluate_alerts({"ram": 50, "cpu": 10, "disk_free_pct": 50,
                                 "online": False}, 0, True)
    report("Монитор: пороги RAM и потеря сети",
           "ram_high" in codes and "net_lost" in codes2)
    codes3, streak3 = evaluate_alerts({"ram": 50, "cpu": 95, "disk_free_pct": 50,
                                       "online": True}, 0, True)
    codes4, _ = evaluate_alerts({"ram": 50, "cpu": 96, "disk_free_pct": 50,
                                 "online": True}, streak3, True)
    report("Монитор: CPU — только после двух проверок подряд",
           "cpu_high" not in codes3 and "cpu_high" in codes4)

    # ================= планировщик =================
    from aura.planner import Planner, split_sequence
    report("Планировщик: разбиение последовательности",
           split_sequence("открой код потом открой браузер")
           == ["открой код", "открой браузер"])
    with tempfile.TemporaryDirectory() as tmp:
        ce = ContextEngine(config={}, journal_path=os.path.join(tmp, "j.json"))
        ce._journal.append({"ts": _t.time() - 86400, "kind": "workflow",
                            "desc": "задача",
                            "actions": [{"type": "open_app", "target": "code"}]})
        plan = Planner().match("сделай как вчера", context=ce)
        report("Планировщик: «сделай как вчера» → план с шагами",
               plan is not None and len(plan.steps) == 1
               and "1." in plan.prompt())
        plan2 = Planner().match("подготовь компьютер к работе", profiles=[])
        report("Планировщик: «подготовь к работе» → шаблон",
               plan2 is not None and len(plan2.steps) == 2
               and plan2.steps[0].command == "открой код")

    # ================= красивая ошибка =================
    from aura.resolver import suggest
    alts = suggest("фотошопчик",
                   installed=lambda t: t in ("krita", "gimp", "paint"))
    report("Resolver: «фотошопчик» → предлагает krita",
           bool(alts) and alts[0] == "krita")

    with tempfile.TemporaryDirectory() as tmp:
        cfgx = Config(os.path.join(tmp, "s.json"))
        from aura.skills.actions import ActionContext, execute_actions
        ctxx = ActionContext(say=lambda x: None, log=lambda *a, **k: None,
                             config=cfgx)
        seen = []
        execute_actions([{"type": "wait", "target": "0"}], ctxx,
                        on_step=lambda i, n, a: seen.append((i, n)))
        report("Действия: колбэк шага (AURA THINKING)", seen == [(1, 1)])

    # ================= мозг: планы и контекст =================
    with tempfile.TemporaryDirectory() as tmp:
        cfg, v, ev, brain = make_brain(tmp)
        brain.context.stop()
        brain._process("сколько времени потом какое сегодня число", "voice")
        spoken = " ".join(v.spoken)
        report("Мозг: последовательность → план с подтверждением",
               "План" in spoken and "шагов 2" in spoken)
        v.spoken.clear()
        brain._process("да")
        deadline = _t.time() + 6
        while _t.time() < deadline and not any(
                "Последовательность" in s for s in v.spoken):
            _t.sleep(0.05)
        report("Мозг: план выполняется после «да»",
               any("Последовательность" in s for s in v.spoken))

        hits = []
        brain._set_choice("Похожее есть:",
                          [("один", lambda: hits.append(1)),
                           ("два", lambda: hits.append(2))])
        brain._process("два", "voice")
        deadline = _t.time() + 4
        while _t.time() < deadline and not hits:
            _t.sleep(0.05)
        report("Мозг: выбор варианта по номеру", hits == [2])

    with tempfile.TemporaryDirectory() as tmp:
        cfg2, v2, ev2, brain2 = make_brain(tmp)
        brain2.context.stop()
        brain2.context._journal.append(
            {"ts": _t.time() - 86400, "kind": "workflow",
             "desc": "утренний ритуал",
             "actions": [{"type": "wait", "target": "0"}]})
        brain2._process("сделай как вчера")
        report("Мозг: «сделай как вчера» предлагает план",
               any("Как вчера" in s for s in v2.spoken))

        v2.spoken.clear()
        brain2._process("что открыто")
        report("Мозг: «что открыто» отвечает из контекста",
               any(("Сейчас" in s) or ("Открыто" in s) for s in v2.spoken))

        v2.spoken.clear()
        brain2._process("закрой это")
        report("Мозг: «закрой это» без активного окна — вежливый отказ",
               any("активного окна" in s for s in v2.spoken))


def check_gui():
    print("\n[3] Интерфейс (PySide6, offscreen)")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        report("PySide6", False, f"нет PySide6: {exc}")
        return
    app = QApplication.instance() or QApplication([])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg, voice, events, brain = make_brain(tmp)
            from aura.gui import MainWindow
            win = MainWindow(cfg, voice, None, brain, events)
            win.resize(1280, 800)
            win.show()
            app.processEvents()
            for state in ("idle", "listening", "thinking", "speaking",
                          "success", "error", "sleep"):
                win.face.set_state(state)
                for _ in range(3):
                    win.face._tick()
                    app.processEvents()
            win.face.set_state("idle")
            ok = (win.tabs.count() == 5 and win.cmd_list is not None
                  and win.perm_combos and win.talk_btn is not None)
            # AURA MODE переключается туда-обратно без падений
            win._toggle_aura_mode()
            win._toggle_aura_mode()
            report("Окно Command Center строится (5 вкладок, AURA MODE)", ok)
            # метрики/пульс/THINKING вместо фейковой ENERGY
            has_new = all(hasattr(win, a) for a in ("sys_lbl", "pulse", "think"))
            report("Интерфейс: CPU/RAM/пульс/THINKING вместо ENERGY",
                   has_new and not hasattr(win, "energy_lbl"))
            win._update_bottom()
            report("Интерфейс: нижняя панель заполнена реальными метриками",
                   "CPU" in win.sys_lbl.text() and "NET" in win.sys_lbl.text())
            # сохраняем скриншот для документации
            shots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "docs")
            os.makedirs(shots_dir, exist_ok=True)
            for state, label in (("idle", "main"), ("listening", "listening"),
                                 ("thinking", "thinking"), ("speaking", "speaking"),
                                 ("success", "success"), ("error", "error"),
                                 ("sleep", "sleep")):
                win.face.set_state(state)
                for _ in range(3):
                    win.face._tick()
                    app.processEvents()
                win.grab().save(os.path.join(shots_dir, f"aura_ui_{label}.png"))
            report("Скриншоты интерфейса сохранены в docs/", True)
            win.close()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        report("UI-дым", False, str(exc))


if __name__ == "__main__":
    print("=" * 56)
    print("  AURA — самопроверка")
    print("=" * 56)
    check_environment()
    try:
        check_logic()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        report("Логика", False, str(exc))
    check_gui()
    passed = sum(1 for r in results if r)
    print("\n" + "=" * 56)
    print(f"  Итог: {passed}/{len(results)} проверок пройдено")
    print("=" * 56)
    sys.exit(0 if passed == len(results) else 1)
