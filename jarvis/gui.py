# -*- coding: utf-8 -*-
"""Пункт управления JARVIS: лицо, журнал, редактор своих команд, настройки."""
import queue
import re
import tkinter as tk
from tkinter import ttk

from .face import FaceCanvas

# ---------- тема ----------
BG = "#0a0f1c"
PANEL = "#111a2e"
PANEL2 = "#0e1526"
FIELD = "#16223a"
FG = "#e2e8f0"
FG_DIM = "#8ea0bf"
ACCENT = "#22d3ee"
ACCENT2 = "#38bdf8"
OK = "#4ade80"
WARN = "#fbbf24"
ERR = "#f87171"

STATE_LABELS = {
    "idle": "Ожидаю…", "listening": "Слушаю…", "thinking": "Думаю…",
    "speaking": "Говорю…", "alert": "Внимание", "off": "Выключен",
}

ACTION_TYPES = ("open_url", "open_app", "shell", "press", "type_text", "volume", "say", "wait")

HINT = ("Формат действий (одна строка = одно действие):  тип | значение\n"
        "  open_url | https://youtube.com\n"
        "  open_app | notepad            shell | ipconfig\n"
        "  press | win+d                 volume | mute\n"
        "  type_text | Привет!           wait | 2\n"
        "  say | Готово, сэр!\n"
        "Фразы — по одной в строке. Для продвинутых: поле «Regex» вместо фраз.")


def parse_actions(text: str):
    """Строки «тип | значение» -> список действий."""
    actions = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        kind, _, value = line.partition("|")
        kind = kind.strip().lower()
        value = value.strip()
        if kind not in ACTION_TYPES or not value:
            continue
        if kind == "say":
            actions.append({"type": "say", "text": value})
        else:
            actions.append({"type": kind, "target": value})
    return actions


def actions_to_text(actions):
    lines = []
    for a in actions or []:
        kind = a.get("type", "")
        value = a.get("text", a.get("target", ""))
        if kind:
            lines.append(f"{kind} | {value}")
    return "\n".join(lines)


class JarvisApp(tk.Tk):
    def __init__(self, config, voice, ear, brain, events: queue.Queue):
        super().__init__()
        self.config_obj = config
        self.voice = voice
        self.ear = ear
        self.brain = brain
        self.events = events
        self.mic_active = False

        self.title("J.A.R.V.I.S. — Пункт управления")
        self.geometry("1180x720")
        self.minsize(960, 620)
        self.configure(bg=BG)
        self._style()
        self._build()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(60, self._poll_events)
        self.after(200, self._bootstrap_mic)

    # ==================== стили ====================
    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(6, 6, 6, 0))
        style.configure("TNotebook.Tab", background=PANEL2, foreground=FG_DIM,
                        padding=(16, 8), font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", FIELD)], foreground=[("selected", ACCENT)])
        style.configure("TCombobox", fieldbackground=FIELD, background=FIELD,
                        foreground=FG, arrowcolor=ACCENT, bordercolor=FIELD,
                        lightcolor=FIELD, darkcolor=FIELD)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
                  foreground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#04121a")

    # ==================== построение ====================
    def _build(self):
        # --- шапка ---
        head = tk.Frame(self, bg=PANEL2, padx=14, pady=8)
        head.pack(fill="x")
        tk.Label(head, text="J.A.R.V.I.S.", font=("Consolas", 16, "bold"),
                 bg=PANEL2, fg=ACCENT).pack(side="left")
        self.head_dot = tk.Label(head, text="●", font=("Segoe UI", 12),
                                 bg=PANEL2, fg=FG_DIM)
        self.head_dot.pack(side="left", padx=(10, 4))
        self.head_status = tk.Label(head, text="инициализация…", font=("Segoe UI", 10),
                                    bg=PANEL2, fg=FG_DIM)
        self.head_status.pack(side="left")
        self.mic_var = tk.BooleanVar(value=bool(self.config_obj.get("mic_enabled", True)))
        self.mic_check = tk.Checkbutton(
            head, text="Слушать микрофон", variable=self.mic_var, command=self._toggle_mic,
            bg=PANEL2, fg=FG, selectcolor=FIELD, activebackground=PANEL2,
            activeforeground=ACCENT, font=("Segoe UI", 10))
        self.mic_check.pack(side="right")

        # --- тело ---
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # левая колонка: лицо
        left = tk.Frame(body, bg=PANEL2, padx=10, pady=10)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        self.face = FaceCanvas(left, width=340, height=340)
        self.face.pack(fill="both", expand=True)
        self.status_label = tk.Label(left, text="Запуск…", font=("Segoe UI", 13, "bold"),
                                     bg=PANEL2, fg=FG)
        self.status_label.pack(pady=(8, 0))
        self.subtitle = tk.Label(left, text="", font=("Segoe UI", 10), wraplength=320,
                                 bg=PANEL2, fg=FG_DIM, justify="center", height=3)
        self.subtitle.pack(fill="x")

        # правая колонка: вкладки
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)
        self.tab_log = tk.Frame(nb, bg=BG)
        self.tab_cmds = tk.Frame(nb, bg=BG)
        self.tab_settings = tk.Frame(nb, bg=BG)
        nb.add(self.tab_log, text="  Журнал  ")
        nb.add(self.tab_cmds, text="  Команды  ")
        nb.add(self.tab_settings, text="  Настройки  ")
        self._build_log(self.tab_log)
        self._build_commands(self.tab_cmds)
        self._build_settings(self.tab_settings)

        # --- нижняя строка ввода ---
        bottom = tk.Frame(self, bg=PANEL2, padx=10, pady=10)
        bottom.pack(fill="x", side="bottom")
        self.entry = tk.Entry(bottom, font=("Segoe UI", 12), bg=FIELD, fg=FG,
                              insertbackground=ACCENT, relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self.entry.bind("<Return>", self._submit)
        tk.Button(bottom, text="Отправить", command=self._submit, bg=ACCENT, fg="#04121a",
                  activebackground=ACCENT2, activeforeground="#04121a", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=16, pady=4, cursor="hand2").pack(side="left")
        tk.Button(bottom, text="🎤 Слушать", command=self._push_talk, bg=FIELD, fg=ACCENT,
                  activebackground=FIELD, activeforeground=ACCENT2, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=16, pady=4, cursor="hand2").pack(
            side="left", padx=(8, 0))

    # --- журнал ---
    def _build_log(self, parent):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(6, 2))
        tk.Label(bar, text="Журнал команд и событий", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Button(bar, text="Очистить", command=self._clear_log, bg=PANEL2, fg=FG_DIM,
                  relief="flat", activebackground=PANEL2, activeforeground=FG,
                  cursor="hand2").pack(side="right")
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(frame, bg=PANEL, fg=FG, relief="flat", padx=12, pady=10,
                           font=("Consolas", 10), wrap="word", state="disabled",
                           insertbackground=FG)
        scroll = ttk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        for tag, color in (("user", ACCENT2), ("jarvis", "#a5b4fc"), ("system", FG_DIM),
                           ("error", ERR)):
            self.log.tag_configure(tag, foreground=color)

    def log_line(self, level: str, msg: str):
        import datetime
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        tag = {"user": "user", "jarvis": "jarvis", "error": "error"}.get(level, "system")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] ", "system")
        self.log.insert("end", msg + "\n", tag)
        if self.log.yview()[1] > 0.9 or level == "user":
            self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # --- вкладка «Команды» ---
    def _build_commands(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        left = tk.Frame(parent, bg=BG, padx=8, pady=8)
        left.grid(row=0, column=0, sticky="ns")
        tk.Label(left, text="Мои команды", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.cmd_list = tk.Listbox(left, bg=PANEL, fg=FG, relief="flat", width=26,
                                   selectbackground=ACCENT, selectforeground="#04121a",
                                   font=("Segoe UI", 10), activestyle="none")
        self.cmd_list.pack(fill="y", expand=True, pady=(4, 6))
        self.cmd_list.bind("<<ListboxSelect>>", self._cmd_selected)
        for text, cmd in (("＋ Новая", self._cmd_new), ("🗑 Удалить", self._cmd_delete),
                          ("⟳ Из файла", self._cmd_reload)):
            tk.Button(left, text=text, command=cmd, bg=FIELD, fg=FG, relief="flat",
                      activebackground=FIELD, activeforeground=ACCENT, cursor="hand2",
                      font=("Segoe UI", 9)).pack(fill="x", pady=2)

        right = tk.Frame(parent, bg=BG, padx=8, pady=8)
        right.grid(row=0, column=1, sticky="nsew")
        f = right

        def label(text, row, col=0):
            tk.Label(f, text=text, bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).grid(
                row=row, column=col, sticky="w", pady=(8, 1))

        self.cmd_name = tk.Entry(f, bg=FIELD, fg=FG, relief="flat", font=("Segoe UI", 11))
        label("Название")
        self.cmd_name.grid(row=1, column=0, columnspan=2, sticky="ew", ipady=5)

        label("Фразы для активации (по одной в строке)")
        self.cmd_phrases = tk.Text(f, bg=FIELD, fg=FG, relief="flat", height=4,
                                   font=("Segoe UI", 10), wrap="word", padx=8, pady=6)
        self.cmd_phrases.grid(row=3, column=0, sticky="nsew")

        label("Regex (необязательно, вместо фраз)")
        self.cmd_regex = tk.Entry(f, bg=FIELD, fg=FG, relief="flat", font=("Consolas", 10))
        self.cmd_regex.grid(row=5, column=0, sticky="ew", ipady=5)

        label("Ответ ассистента (необязательно, иначе — действие say или стандартный)")
        self.cmd_reply = tk.Entry(f, bg=FIELD, fg=FG, relief="flat", font=("Segoe UI", 10))
        self.cmd_reply.grid(row=7, column=0, sticky="ew", ipady=5)

        label("Действия")
        self.cmd_actions = tk.Text(f, bg=FIELD, fg=FG, relief="flat", height=7,
                                   font=("Consolas", 10), wrap="word", padx=8, pady=6)
        self.cmd_actions.grid(row=9, column=0, sticky="nsew")

        f.rowconfigure(3, weight=1)
        f.rowconfigure(9, weight=2)
        f.columnconfigure(0, weight=1)

        tk.Button(f, text="💾 Сохранить команду", command=self._cmd_save, bg=ACCENT,
                  fg="#04121a", relief="flat", font=("Segoe UI", 10, "bold"), padx=14,
                  pady=5, cursor="hand2").grid(row=10, column=0, sticky="w", pady=(10, 2))
        tk.Label(f, text=HINT, bg=BG, fg=FG_DIM, font=("Consolas", 8),
                 justify="left").grid(row=11, column=0, sticky="w", pady=(4, 0))
        self._fill_cmd_list()

    def _fill_cmd_list(self):
        self.cmd_list.delete(0, "end")
        for name in self.brain.custom.names():
            self.cmd_list.insert("end", name)

    def _cmd_selected(self, _evt=None):
        sel = self.cmd_list.curselection()
        if not sel:
            return
        cmd = self.brain.custom.get(self.cmd_list.get(sel[0]))
        if not cmd:
            return
        self.cmd_name.delete(0, "end")
        self.cmd_name.insert(0, cmd.get("name", ""))
        self.cmd_phrases.delete("1.0", "end")
        self.cmd_phrases.insert("1.0", "\n".join(cmd.get("phrases", [])))
        self.cmd_regex.delete(0, "end")
        self.cmd_regex.insert(0, cmd.get("pattern", ""))
        self.cmd_reply.delete(0, "end")
        self.cmd_reply.insert(0, cmd.get("reply", ""))
        self.cmd_actions.delete("1.0", "end")
        self.cmd_actions.insert("1.0", actions_to_text(cmd.get("actions", [])))

    def _cmd_new(self):
        for w in (self.cmd_name, self.cmd_regex, self.cmd_reply):
            w.delete(0, "end")
        for w in (self.cmd_phrases, self.cmd_actions):
            w.delete("1.0", "end")
        self.cmd_name.focus_set()

    def _cmd_save(self):
        name = self.cmd_name.get().strip()
        phrases = [p.strip() for p in self.cmd_phrases.get("1.0", "end").splitlines() if p.strip()]
        actions = parse_actions(self.cmd_actions.get("1.0", "end"))
        if not name:
            self.log_line("error", "Укажите название команды.")
            return
        if not phrases and not self.cmd_regex.get().strip():
            self.log_line("error", "Добавьте хотя бы одну фразу или regex.")
            return
        if not actions:
            self.log_line("error", "Добавьте хотя бы одно действие (тип | значение).")
            return
        cmd = {"name": name, "phrases": phrases, "actions": actions}
        if self.cmd_regex.get().strip():
            cmd["pattern"] = self.cmd_regex.get().strip()
        if self.cmd_reply.get().strip():
            cmd["reply"] = self.cmd_reply.get().strip()
        self.brain.custom.upsert(cmd)
        self._fill_cmd_list()
        self.log_line("system", f"Команда «{name}» сохранена ({len(actions)} действий).")

    def _cmd_delete(self):
        sel = self.cmd_list.curselection()
        if not sel:
            return
        name = self.cmd_list.get(sel[0])
        self.brain.custom.delete(name)
        self._fill_cmd_list()
        self._cmd_new()
        self.log_line("system", f"Команда «{name}» удалена.")

    def _cmd_reload(self):
        self.brain.custom.load()
        self._fill_cmd_list()
        self.log_line("system", "Команды перечитаны из файла.")

    # --- вкладка «Настройки» ---
    def _build_settings(self, parent):
        wrap = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vs = ttk.Scrollbar(parent, orient="vertical", command=wrap.yview)
        form = tk.Frame(wrap, bg=BG, padx=14, pady=10)
        form.bind("<Configure>",
                  lambda e: wrap.configure(scrollregion=wrap.bbox("all")))
        _win_id = wrap.create_window((0, 0), window=form, anchor="nw", width=640)
        wrap.bind("<Configure>",
                  lambda e: wrap.itemconfig(_win_id, width=max(e.width, 480)))
        wrap.configure(yscrollcommand=vs.set)
        wrap.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        wrap.bind_all("<MouseWheel>", lambda e: wrap.yview_scroll(-e.delta // 120, "units"))

        c = self.config_obj
        row = [0]

        def section(title):
            tk.Label(form, text=title, bg=BG, fg=ACCENT, font=("Segoe UI", 11, "bold")).grid(
                row=row[0], column=0, columnspan=2, sticky="w", pady=(14, 4))
            row[0] += 1

        def field(title, key, width=46, show=""):
            tk.Label(form, text=title, bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).grid(
                row=row[0], column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(c.get(key, "") or ""))
            e = tk.Entry(form, textvariable=var, bg=FIELD, fg=FG, relief="flat",
                         width=width, show=show, font=("Segoe UI", 10))
            e.grid(row=row[0], column=1, sticky="ew", ipady=4, padx=(10, 0))
            self._set_vars[key] = var
            row[0] += 1

        def check(title, key):
            var = tk.BooleanVar(value=bool(c.get(key)))
            tk.Checkbutton(form, text=title, variable=var, bg=BG, fg=FG,
                           selectcolor=FIELD, activebackground=BG, activeforeground=ACCENT,
                           font=("Segoe UI", 10)).grid(row=row[0], column=0, columnspan=2,
                                                       sticky="w", pady=2)
            self._set_vars[key] = var
            row[0] += 1

        def slider(title, key, frm, to, fmt="{:.0f}"):
            tk.Label(form, text=title, bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).grid(
                row=row[0], column=0, sticky="w", pady=3)
            var = tk.DoubleVar(value=float(c.get(key, frm)))
            lbl = tk.Label(form, text=fmt.format(var.get()), bg=BG, fg=ACCENT,
                           font=("Segoe UI", 9), width=6)
            s = ttk.Scale(form, from_=frm, to=to, variable=var,
                          command=lambda v, vv=var, ll=lbl, ff=fmt: ll.configure(
                              text=ff.format(vv.get())))
            s.grid(row=row[0], column=1, sticky="ew", padx=(10, 4))
            lbl.grid(row=row[0], column=1, sticky="e", padx=(0, 0))
            self._set_vars[key] = var
            row[0] += 1

        def combo(title, key, values, width=44):
            tk.Label(form, text=title, bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).grid(
                row=row[0], column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(c.get(key, "") or (values[0] if values else "")))
            cb = ttk.Combobox(form, textvariable=var, values=values, width=width,
                              state="readonly")
            cb.grid(row=row[0], column=1, sticky="ew", padx=(10, 0))
            self._set_vars[key] = var
            row[0] += 1

        self._set_vars = {}
        form.columnconfigure(1, weight=1)

        section("🎙 Голос (озвучка ответов)")
        check("Озвучивать ответы", "tts_enabled")
        slider("Скорость речи", "tts_rate", 100, 260)
        slider("Громкость речи", "tts_volume", 0.0, 1.0, "{:.0%}")
        tk.Label(form, text="Голос", bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).grid(
            row=row[0], column=0, sticky="w", pady=3)
        _voices = self.voice.available_voices()
        self.voice_names = ["По умолчанию"] + [n for _, n in _voices]
        self.voice_ids = [""] + [i for i, _ in _voices]
        self.voice_var = tk.StringVar(value="По умолчанию")
        cur = c.get("tts_voice_id", "")
        if cur in self.voice_ids:
            self.voice_var.set(self.voice_names[self.voice_ids.index(cur)])
        ttk.Combobox(form, textvariable=self.voice_var, values=self.voice_names,
                     state="readonly", width=44).grid(row=row[0], column=1, sticky="ew",
                                                      padx=(10, 0))
        row[0] += 1
        tk.Button(form, text="Тест голоса", command=lambda: self.voice.say(
            "Привет! Проверка голоса завершена успешно."),
            bg=FIELD, fg=FG, relief="flat", activebackground=FIELD,
            activeforeground=ACCENT, cursor="hand2").grid(row=row[0], column=1,
                                                          sticky="w", pady=(4, 0))
        row[0] += 1

        section("👂 Слух (распознавание речи)")
        field("Кодовое слово", "wake_word", 20)
        check("Требовать кодовое слово", "require_wake_word")
        combo("Язык распознавания", "language",
              ["ru-RU", "en-US", "uk-UA", "de-DE", "fr-FR", "es-ES"])
        combo("Движок распознавания", "stt_engine", ["google", "vosk"])
        field("Путь к модели Vosk (офлайн)", "vosk_model_path")

        section("👤 Персонализация")
        field("Как меня называть", "user_name", 20)
        field("Город для погоды", "city", 20)
        check("Подтверждать выключение ПК", "confirm_power")
        field("Ссылка «включи музыку»", "music_url")
        field("Папка для скриншотов", "screenshots_dir")

        section("🤖 Нейросеть (OpenAI-совместимый API)")
        check("Отвечать через ИИ, если команда не распознана", "ai_enabled")
        field("Base URL", "ai_base_url")
        field("API-ключ", "ai_api_key", show="•")
        field("Модель", "ai_model", 24)
        check("Разрешить ИИ выполнять действия на ПК", "ai_allow_actions")
        tk.Button(form, text="Проверить связь с ИИ", command=self._test_ai, bg=FIELD, fg=FG,
                  relief="flat", activebackground=FIELD, activeforeground=ACCENT,
                  cursor="hand2").grid(row=row[0], column=1, sticky="w", pady=(4, 0))
        row[0] += 1

        section("💾 Применение")
        tk.Button(form, text="СОХРАНИТЬ НАСТРОЙКИ", command=self._save_settings,
                  bg=ACCENT, fg="#04121a", relief="flat", font=("Segoe UI", 11, "bold"),
                  padx=18, pady=6, cursor="hand2").grid(row=row[0], column=0,
                                                        columnspan=2, sticky="w")
        self.save_status = tk.Label(form, text="", bg=BG, fg=OK, font=("Segoe UI", 9))
        self.save_status.grid(row=row[0], column=1, sticky="e")

    # ==================== действия ====================
    def _bootstrap_mic(self):
        self.log_line("system", "JARVIS запущен. Введите команду или включите микрофон.")
        if self.mic_var.get():
            self._toggle_mic(turn_on=True)

    def _toggle_mic(self, turn_on=None):
        enable = self.mic_var.get() if turn_on is None else turn_on
        self.mic_var.set(enable)
        if enable:
            ok = self.ear.start()
            self.log_line("system", "Микрофон включается…" if ok else
                          "Микрофон недоступен — работаем с клавиатуры.")
        else:
            self.ear.stop()
            self.mic_active = False
            self.face.set_state("off")
            self._set_status("Микрофон выключен", "off")
            self.log_line("system", "Микрофон выключен.")

    def _push_talk(self):
        if not self.ear.listen_once():
            self.log_line("error", "Микрофон недоступен. Проверьте PyAudio/устройство.")
        else:
            self._set_status("Слушаю…", "listening")

    def _submit(self, _evt=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.brain.handle(text, "text")

    def _test_ai(self):
        self._apply_settings_to_config()
        self.config_obj.save()

        def run():
            try:
                reply = self.brain.ai.test_connection()
                self.events.put({"kind": "log", "level": "system", "msg": f"ИИ отвечает: «{reply}»"})
                self.events.put({"kind": "log", "level": "system", "msg": "Связь с ИИ работает ✅"})
            except Exception as exc:
                self.events.put({"kind": "log", "level": "error",
                                 "msg": f"ИИ не отвечает: {exc}"})
        import threading
        threading.Thread(target=run, daemon=True).start()
        self.log_line("system", "Проверяю связь с ИИ…")

    def _apply_settings_to_config(self):
        v = self._set_vars
        for key in ("tts_enabled", "require_wake_word", "confirm_power", "ai_enabled",
                    "ai_allow_actions"):
            if key in v:
                self.config_obj.set(key, bool(v[key].get()))
        for key in ("wake_word", "language", "stt_engine", "vosk_model_path", "user_name",
                    "city", "music_url", "screenshots_dir", "ai_base_url", "ai_api_key",
                    "ai_model"):
            if key in v:
                self.config_obj.set(key, str(v[key].get()).strip())
        for key in ("tts_rate", "tts_volume"):
            if key in v:
                val = float(v[key].get())
                self.config_obj.set(key, int(val) if key == "tts_rate" else val)
        idx = self.voice_names.index(self.voice_var.get())
        self.config_obj.set("tts_voice_id", self.voice_ids[idx])

    def _save_settings(self):
        self._apply_settings_to_config()
        self.config_obj.save()
        self.save_status.configure(text="Сохранено ✓")
        self.after(2500, lambda: self.save_status.configure(text=""))
        self.log_line("system", "Настройки сохранены.")

    # ==================== события из фоновых потоков ====================
    def _poll_events(self):
        try:
            while True:
                evt = self.events.get_nowait()
                try:
                    self._handle_event(evt)
                except tk.TclError:
                    return
        except queue.Empty:
            pass
        self.after(60, self._poll_events)

    def _handle_event(self, evt):
        kind = evt.get("kind")
        if kind == "log":
            self.log_line(evt.get("level", "system"), evt.get("msg", ""))
        elif kind == "state":
            self.face.set_state(evt["name"])
            self._set_status(evt.get("label") or STATE_LABELS.get(evt["name"], ""),
                             evt["name"])
        elif kind == "heard":
            self.subtitle.configure(text=f"Вы: {evt['text']}")
        elif kind == "say_start":
            self.face.set_state("speaking")
            self._set_status("Говорю…", "speaking")
            self.log_line("jarvis", f"🤖 {evt.get('text', '')}")
            self.subtitle.configure(text=f"JARVIS: {evt.get('text', '')[:120]}")
        elif kind == "say_end":
            if self.mic_active:
                self.face.set_state("listening")
                self._set_status("Слушаю…", "listening")
            else:
                self.face.set_state("idle")
                self._set_status("Ожидаю…", "idle")
        elif kind == "mic_state":
            self.mic_active = bool(evt.get("active"))
            if self.mic_active:
                self.face.set_state("listening")
                self._set_status("Слушаю…", "listening")

    def _set_status(self, text, state="idle"):
        colors = {"listening": ACCENT, "thinking": "#b48cff", "speaking": OK,
                  "alert": ERR, "idle": FG_DIM, "off": FG_DIM}
        self.status_label.configure(text=text, fg=colors.get(state, FG))
        self.head_status.configure(text=f"{text}")
        self.head_dot.configure(fg=colors.get(state, FG_DIM))

    # ==================== завершение ====================
    def on_close(self):
        try:
            self.ear.stop()
            self.voice.shutdown()
            self.face.stop()
        finally:
            self.destroy()
