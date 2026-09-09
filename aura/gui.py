# -*- coding: utf-8 -*-
"""AURA Command Center — главное окно (PySide6).

Тёмный sci-fi интерфейс: лицо-состояние, статистика системы, вкладки
(Диалог, Активность, Команды, Режимы, Память, Разрешения, Настройки).
"""
import os
import queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSlider, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget, QSizePolicy,
)

from .face_avatar import FaceImageWidget
from .face_qt import FaceWidget

from .face_qt import FaceWidget

# ---------- тема ----------
BG = "#0a0f1c"
PANEL = "#111a2e"
PANEL2 = "#0e1526"
FIELD = "#16223a"
LINE = "#1b2740"
FG = "#e2e8f0"
FG_DIM = "#8ea0bf"
ACCENT = "#22d3ee"
OK = "#4ade80"
WARN = "#fbbf24"
ERR = "#f87171"

STATE_LABELS = {
    "idle": "Ожидаю…", "listening": "Слушаю…", "thinking": "Думаю…",
    "speaking": "Говорю…", "success": "Готово ✓", "error": "Ошибка",
    "alert": "Внимание", "sleep": "Дремлю…", "off": "Выключена",
}
STATE_COLORS_UI = {
    "listening": ACCENT, "thinking": "#b48cff", "speaking": OK,
    "success": OK, "error": ERR, "alert": WARN, "idle": FG_DIM,
    "sleep": FG_DIM, "off": FG_DIM,
}

MOOD_EMOJI = {"neutral": "😐", "happy": "😊", "curious": "🤔", "sleepy": "😴",
              "annoyed": "😤", "confident": "😎", "concerned": "😨"}

ACTION_DEFS = {
    "open_app": ("Запустить приложение", "путь или имя, напр.: code, C:/app.exe"),
    "open_url": ("Открыть сайт", "https://youtube.com"),
    "close_app": ("Закрыть приложение", "имя процесса: chrome"),
    "type_text": ("Напечатать текст", "текст для вставки"),
    "press": ("Нажать клавиши", "например: win+d, ctrl+s"),
    "click": ("Клик мышью", "координаты: 960,540"),
    "scroll": ("Прокрутка", "-500 (вниз) или 300 (вверх)"),
    "shell": ("Команда системы", "например: ipconfig"),
    "run_python": ("Запустить Python", "print('Привет, AURA!')"),
    "volume": ("Громкость", "0–100 / up / down / mute"),
    "brightness": ("Яркость экрана", "5–100"),
    "create_folder": ("Создать папку", "путь новой папки"),
    "write_file": ("Записать файл", "путь | содержимое"),
    "zip_folder": ("ZIP папки", "путь папки"),
    "rename_path": ("Переименовать", "старый путь | новый путь"),
    "move_path": ("Переместить", "откуда | куда"),
    "delete_path": ("Удалить (в корзину AURA)", "путь"),
    "say": ("Сказать фразу", "фраза для озвучки"),
    "wait": ("Пауза, сек", "2"),
    "ai": ("Поручение ИИ", "что сделать средствами ИИ"),
}
ACTION_ORDER = list(ACTION_DEFS.keys())

STYLESHEET = f"""
QMainWindow, QWidget {{ background: {BG}; color: {FG};
    font-family: 'Segoe UI', 'Ubuntu', sans-serif; font-size: 10pt; }}
QLabel#title {{ font-size: 17pt; font-weight: 800; color: {ACCENT};
    letter-spacing: 3px; }}
QLabel#dim {{ color: {FG_DIM}; }}
QLabel#accent {{ color: {ACCENT}; }}
QLabel#ok {{ color: {OK}; }}
QLabel#err {{ color: {ERR}; }}
QFrame#panel, QGroupBox {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 12px; }}
QGroupBox {{ margin-top: 12px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: {ACCENT}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: {PANEL2}; color: {FG_DIM}; padding: 8px 14px;
    border-top-left-radius: 9px; border-top-right-radius: 9px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {FIELD}; color: {ACCENT}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox {{
    background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px;
    padding: 6px; color: {FG}; selection-background-color: {ACCENT}; }}
QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px;
    padding: 5px 10px; color: {FG}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; color: {FG};
    selection-background-color: {ACCENT}; selection-color: #04121a; }}
QPushButton {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px;
    padding: 7px 14px; color: {FG}; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {PANEL}; }}
QPushButton#accent {{ background: {ACCENT}; color: #04121a; font-weight: 700;
    border: none; }}
QPushButton#accent:hover {{ background: #67e8f9; color: #04121a; }}
QPushButton#danger {{ color: {ERR}; }}
QPushButton:checked {{ border-color: {ACCENT}; color: {ACCENT};
    background: {PANEL}; }}
QListWidget, QTreeWidget, QTableWidget {{ background: {PANEL};
    border: 1px solid {LINE}; border-radius: 10px; padding: 4px; }}
QListWidget::item, QTreeWidget::item {{ padding: 5px; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {ACCENT}; color: #04121a; }}
QHeaderView::section {{ background: {PANEL2}; color: {FG_DIM}; border: none;
    padding: 6px; }}
QProgressBar {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 7px;
    text-align: center; color: {FG}; height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QSlider::groove:horizontal {{ height: 6px; background: {FIELD};
    border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; background: {ACCENT};
    border-radius: 8px; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background: {FIELD}; border-radius: 5px;
    min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px;
    border: 1px solid {LINE}; background: {FIELD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
"""


# ==========================================================================
# Виджеты-помощники
# ==========================================================================
class StatLabel(QLabel):
    """CPU / RAM / диск в шапке."""

    def __init__(self, parent=None):
        super().__init__("—", parent)
        self.setObjectName("dim")
        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(2500)
        self.refresh()

    def refresh(self):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            self.setText(f"CPU {cpu:.0f}%   RAM {ram:.0f}%")
        except Exception:
            self.setText("")


class ActionEditDialog(QDialog):
    """Диалог добавления/правки одного действия."""

    def __init__(self, parent=None, action=None):
        super().__init__(parent)
        self.setWindowTitle("Действие")
        self.setMinimumWidth(520)
        self.action = dict(action or {})
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.type_combo = QComboBox()
        for key in ACTION_ORDER:
            self.type_combo.addItem(ACTION_DEFS[key][0], key)
        # известные, но не вошедшие в список типы тоже покажем
        self.target_edit = QLineEdit()
        self.hint = QLabel("")
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)
        form.addRow("Тип:", self.type_combo)
        form.addRow("Значение:", self.target_edit)
        lay.addLayout(form)
        lay.addWidget(self.hint)
        btns = QHBoxLayout()
        ok = QPushButton("Готово")
        ok.setObjectName("accent")
        cancel = QPushButton("Отмена")
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.type_combo.currentIndexChanged.connect(self._update_hint)
        if self.action:
            key = self.action.get("type", "open_app")
            idx = ACTION_ORDER.index(key) if key in ACTION_ORDER else 0
            self.type_combo.setCurrentIndex(idx)
            self.target_edit.setText(self.action.get("text", self.action.get("target", "")))
        self._update_hint()

    def _update_hint(self):
        key = self.type_combo.currentData()
        self.hint.setText("Пример: " + ACTION_DEFS.get(key, ("", ""))[1])

    def get_action(self):
        key = self.type_combo.currentData()
        value = self.target_edit.text().strip()
        if key == "say":
            return {"type": "say", "text": value}
        return {"type": key, "target": value}


class WorkflowEditor(QWidget):
    """Редактор цепочки действий (используется в Командах и Режимах)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.listw = QListWidget()
        self.listw.itemDoubleClicked.connect(lambda _: self._edit())
        lay.addWidget(self.listw, 1)

        add_row = QGridLayout()
        add_row.setSpacing(4)
        for i, key in enumerate(ACTION_ORDER):
            btn = QPushButton("＋ " + ACTION_DEFS[key][0])
            btn.setToolTip("Добавить: " + ACTION_DEFS[key][1])
            btn.clicked.connect(lambda _=False, k=key: self._add(k))
            add_row.addWidget(btn, i // 3, i % 3)
        lay.addLayout(add_row)

        ctrl = QHBoxLayout()
        for text, fn in (("↑", lambda: self._move(-1)), ("↓", lambda: self._move(1)),
                         ("✖ Удалить", self._remove), ("✎ Править", self._edit)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            ctrl.addWidget(b)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

    # ---- API ----
    def set_actions(self, actions):
        self.listw.clear()
        for a in actions or []:
            self.listw.addItem(self._describe(a))

    def get_actions(self):
        return self._actions_from_list()

    # ---- внутреннее ----
    @staticmethod
    def _describe(a):
        key = a.get("type", "?")
        title = ACTION_DEFS.get(key, (key, ""))[0]
        value = a.get("text", a.get("target", ""))
        return f"{title}  →  {value}"

    def _actions_from_list(self):
        actions = []
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            a = item.data(Qt.UserRole)
            if a:
                actions.append(a)
        return actions

    def _sync(self):
        actions = self._actions_from_list()
        self.set_actions(actions)

    def _add(self, key):
        dlg = ActionEditDialog(self, {"type": key, "target": ""})
        if dlg.exec():
            item = QListWidgetItem(self._describe(dlg.get_action()))
            item.setData(Qt.UserRole, dlg.get_action())
            self.listw.addItem(item)

    def _edit(self):
        row = self.listw.currentRow()
        if row < 0:
            return
        item = self.listw.item(row)
        dlg = ActionEditDialog(self, item.data(Qt.UserRole))
        if dlg.exec():
            item.setText(self._describe(dlg.get_action()))
            item.setData(Qt.UserRole, dlg.get_action())

    def _remove(self):
        row = self.listw.currentRow()
        if row >= 0:
            self.listw.takeItem(row)

    def _move(self, delta):
        row = self.listw.currentRow()
        if row < 0:
            return
        item = self.listw.takeItem(row)
        self.listw.insertItem(max(0, min(self.listw.count(), row + delta)), item)
        self.listw.setCurrentRow(row + delta)


# ==========================================================================
# Главное окно
# ==========================================================================
class MainWindow(QMainWindow):
    def __init__(self, config, voice, ear, brain, events: queue.Queue,
                 hotkeys=None, recorder=None):
        super().__init__()
        self.config_obj = config
        self.voice = voice
        self.ear = ear
        self.brain = brain
        self.events = events
        self.hotkeys = hotkeys
        self.recorder = recorder
        self.mic_active = False

        self.setWindowTitle("AURA · Аврора — Command Center")
        self.resize(1280, 800)
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(STYLESHEET)

        self._build()
        self._recording = False

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_events)
        self.poll_timer.start(50)
        self.mood_timer = QTimer(self)
        self.mood_timer.timeout.connect(brain.mood.tick)
        self.mood_timer.start(30_000)

        QTimer.singleShot(300, self._bootstrap)

    # ------------------------------------------------------------------
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        # ------------------- шапка -------------------
        head = QFrame()
        head.setObjectName("panel")
        h = QHBoxLayout(head)
        h.setContentsMargins(16, 8, 16, 8)
        title = QLabel("A U R A")
        title.setObjectName("title")
        h.addWidget(title)
        sub = QLabel("· АВРОРА · personal AI")
        sub.setObjectName("dim")
        h.addWidget(sub)
        h.addSpacing(14)
        self.dot = QLabel("●")
        self.dot.setObjectName("dim")
        h.addWidget(self.dot)
        self.status = QLabel("инициализация…")
        self.status.setObjectName("dim")
        h.addWidget(self.status)
        h.addStretch(1)
        self.perm_badge = QLabel("")
        self.perm_badge.setObjectName("accent")
        h.addWidget(self.perm_badge)
        self.stats = StatLabel()
        h.addWidget(self.stats)
        self.mic_btn = QPushButton("🎙 Микрофон")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setChecked(bool(self.config_obj.get("mic_enabled", True)))
        self.mic_btn.toggled.connect(self._toggle_mic)
        h.addWidget(self.mic_btn)
        root.addWidget(head)

        # ------------------- тело -------------------
        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        # ----- левая колонка: лицо -----
        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(380)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 14, 12)
        if FaceImageWidget.images_available():
            self.face = FaceImageWidget()      # портрет-аватар (SIGNALIS-стиль)
        else:
            self.face = FaceWidget()           # рисованный HUD-вариант
        self.face.setMinimumHeight(330)
        lv.addWidget(self.face, 1)
        self.state_label = QLabel("Запуск…")
        self.state_label.setAlignment(Qt.AlignCenter)
        f = self.state_label.font()
        f.setPointSize(13)
        f.setBold(True)
        self.state_label.setFont(f)
        lv.addWidget(self.state_label)
        self.mood_label = QLabel("😐 нейтрально")
        self.mood_label.setObjectName("dim")
        self.mood_label.setAlignment(Qt.AlignCenter)
        lv.addWidget(self.mood_label)
        self.energy = QProgressBar()
        self.energy.setRange(0, 100)
        self.energy.setValue(87)
        self.energy.setFormat("энергия %p%")
        self.energy.setFixedHeight(16)
        lv.addWidget(self.energy)
        self.subtitle = QLabel("Готова, когда вы готовы.")
        self.subtitle.setObjectName("dim")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setMinimumHeight(46)
        lv.addWidget(self.subtitle)

        btns = QHBoxLayout()
        talk = QPushButton("🎤 Слушать")
        talk.setObjectName("accent")
        talk.clicked.connect(self._push_talk)
        vis = QPushButton("👁 VISION")
        vis.setToolTip("Сделать скриншот и спросить ИИ, что на экране")
        vis.clicked.connect(self._vision)
        undo = QPushButton("⏪ Отменить")
        undo.clicked.connect(lambda: self.brain.undo_last_async())
        teach = QPushButton("⏺ Учить")
        teach.setToolTip("Teach Mode: записать ваши действия в команду")
        teach.clicked.connect(self._teach)
        for b in (talk, vis, undo, teach):
            btns.addWidget(b)
        lv.addLayout(btns)

        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Режим:"))
        self.profile_combo = QComboBox()
        self._fill_profiles_combo()
        prof_row.addWidget(self.profile_combo, 1)
        run = QPushButton("▶")
        run.setFixedWidth(40)
        run.clicked.connect(self._run_profile_combo)
        prof_row.addWidget(run)
        lv.addLayout(prof_row)

        body.addWidget(left)

        # ----- правая колонка: вкладки -----
        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 1)
        self.tab_chat = QWidget()
        self.tab_cmds = QWidget()
        self.tab_profiles = QWidget()
        self.tab_perms = QWidget()
        self.tab_settings = QWidget()
        for label, widget in (("💬 Диалог", self.tab_chat), ("⚡ Команды", self.tab_cmds),
                              ("🎮 Режимы", self.tab_profiles),
                              ("🛡 Разрешения", self.tab_perms),
                              ("⚙ Настройки", self.tab_settings)):
            self.tabs.addTab(widget, label)
        self._build_chat(self.tab_chat)
        self._build_commands(self.tab_cmds)
        self._build_profiles(self.tab_profiles)
        self._build_perms(self.tab_perms)
        self._build_settings(self.tab_settings)

        # ------------------- нижняя строка -------------------
        bottom = QFrame()
        bottom.setObjectName("panel")
        b = QHBoxLayout(bottom)
        b.setContentsMargins(12, 8, 12, 8)
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "Скажите или напишите: «аврора, включи рабочий режим»…")
        self.input.returnPressed.connect(self._submit)
        b.addWidget(self.input, 1)
        send = QPushButton("Отправить")
        send.setObjectName("accent")
        send.clicked.connect(self._submit)
        b.addWidget(send)
        root.addWidget(bottom)

        self._refresh_perm_badge()

    # ==================================================================
    # вкладки
    # ==================================================================
    def _build_chat(self, tab):
        split = QHBoxLayout(tab)
        split.setContentsMargins(0, 0, 0, 0)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        split.addWidget(self.chat, 3)
        right = QVBoxLayout()
        cap = QLabel("Активность")
        cap.setObjectName("dim")
        right.addWidget(cap)
        self.activity_tree = QTreeWidget()
        self.activity_tree.setHeaderLabels(["Время", "Действие"])
        self.activity_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.activity_tree.setRootIsDecorated(False)
        self.activity_tree.setMaximumWidth(280)
        right.addWidget(self.activity_tree, 1)
        undo = QPushButton("⏪ Отменить последнее")
        undo.clicked.connect(lambda: self.brain.undo_last_async())
        right.addWidget(undo)
        split.addLayout(right)
        self._chat_line("system", "AURA запущена. Готова к работе.")

    def _chat_line(self, level, msg):
        colors = {"user": ACCENT, "aura": "#a5b4fc", "system": FG_DIM, "error": ERR}
        icons = {"user": "🗣", "aura": "💠", "system": "•", "error": "✖"}
        safe = (msg or "").replace("&", "&amp;").replace("<", "&lt;")
        self.chat.append(
            f"<span style='color:{FG_DIM};font-size:8pt'>"
            f"{icons.get(level, '•')} </span>"
            f"<span style='color:{colors.get(level, FG_DIM)}'>{safe}</span>")

    def _build_commands(self, tab):
        lay = QGridLayout(tab)
        # слева список
        left = QVBoxLayout()
        lbl = QLabel("Мои команды")
        lbl.setObjectName("dim")
        left.addWidget(lbl)
        self.cmd_list = QListWidget()
        self.cmd_list.currentRowChanged.connect(self._cmd_selected)
        left.addWidget(self.cmd_list, 1)
        for text, fn in (("＋ Новая", self._cmd_new),
                         ("🗑 Удалить", self._cmd_delete),
                         ("⟳ Из файла", self._cmd_reload)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            left.addWidget(btn)
        lay.addLayout(left, 0, 0)
        # справа форма
        right = QGridLayout()
        right.setVerticalSpacing(4)

        def lab(text):
            l = QLabel(text)
            l.setObjectName("dim")
            return l

        right.addWidget(lab("Название"), 0, 0)
        self.cmd_name = QLineEdit()
        right.addWidget(self.cmd_name, 1, 0)
        right.addWidget(lab("Фразы активации (по одной в строке)"), 2, 0)
        self.cmd_phrases = QPlainTextEdit()
        self.cmd_phrases.setMaximumHeight(80)
        right.addWidget(self.cmd_phrases, 3, 0)
        row2 = QHBoxLayout()
        box = QVBoxLayout()
        box.addWidget(lab("Regex (вместо фраз, для продвинутых)"))
        self.cmd_regex = QLineEdit()
        box.addWidget(self.cmd_regex)
        row2.addLayout(box, 1)
        box2 = QVBoxLayout()
        box2.addWidget(lab("Ответ ассистента"))
        self.cmd_reply = QLineEdit()
        box2.addWidget(self.cmd_reply)
        row2.addLayout(box2, 1)
        right.addLayout(row2, 4, 0)
        right.addWidget(lab("Действия (двойной клик — правка):"), 5, 0)
        self.cmd_actions = WorkflowEditor()
        right.addWidget(self.cmd_actions, 6, 0)
        save = QPushButton("💾 Сохранить команду")
        save.setObjectName("accent")
        save.clicked.connect(self._cmd_save)
        right.addWidget(save, 7, 0)
        lay.addLayout(right, 0, 1)
        lay.setColumnStretch(1, 2)
        self._fill_cmd_list()

    def _fill_cmd_list(self):
        self.cmd_list.blockSignals(True)
        self.cmd_list.clear()
        for name in self.brain.custom.names():
            self.cmd_list.addItem(name)
        self.cmd_list.blockSignals(False)

    def _cmd_selected(self, row):
        if row < 0:
            return
        cmd = self.brain.custom.get(self.cmd_list.item(row).text())
        if not cmd:
            return
        self.cmd_name.setText(cmd.get("name", ""))
        self.cmd_phrases.setPlainText("\n".join(cmd.get("phrases", [])))
        self.cmd_regex.setText(cmd.get("pattern", ""))
        self.cmd_reply.setText(cmd.get("reply", ""))
        self.cmd_actions.set_actions(cmd.get("actions", []))

    def _cmd_new(self):
        self.cmd_list.blockSignals(True)
        self.cmd_list.clearSelection()
        self.cmd_list.blockSignals(False)
        self.cmd_name.clear()
        self.cmd_phrases.clear()
        self.cmd_regex.clear()
        self.cmd_reply.clear()
        self.cmd_actions.set_actions([])
        self.cmd_name.setFocus()

    def _cmd_save(self):
        name = self.cmd_name.text().strip()
        phrases = [p.strip() for p in self.cmd_phrases.toPlainText().splitlines()
                   if p.strip()]
        actions = self.cmd_actions.get_actions()
        if not name:
            self._chat_line("error", "Укажите название команды.")
            return
        if not phrases and not self.cmd_regex.text().strip():
            self._chat_line("error", "Добавьте хотя бы одну фразу или regex.")
            return
        if not actions:
            self._chat_line("error", "Добавьте хотя бы одно действие.")
            return
        cmd = {"name": name, "phrases": phrases, "actions": actions}
        if self.cmd_regex.text().strip():
            cmd["pattern"] = self.cmd_regex.text().strip()
        if self.cmd_reply.text().strip():
            cmd["reply"] = self.cmd_reply.text().strip()
        self.brain.custom.upsert(cmd)
        self._fill_cmd_list()
        self._chat_line("system", f"Команда «{name}» сохранена ({len(actions)} действий).")

    def _cmd_delete(self):
        row = self.cmd_list.currentRow()
        if row < 0:
            return
        name = self.cmd_list.item(row).text()
        self.brain.custom.delete(name)
        self._fill_cmd_list()
        self._cmd_new()
        self._chat_line("system", f"Команда «{name}» удалена.")

    def _cmd_reload(self):
        self.brain.custom.load()
        self._fill_cmd_list()

    # ------------------- режимы -------------------
    def _build_profiles(self, tab):
        lay = QGridLayout(tab)
        left = QVBoxLayout()
        lbl = QLabel("Режимы (профили)")
        lbl.setObjectName("dim")
        left.addWidget(lbl)
        self.prof_list = QListWidget()
        self.prof_list.currentRowChanged.connect(self._prof_selected)
        left.addWidget(self.prof_list, 1)
        for text, fn in (("＋ Новый", self._prof_new),
                         ("🗑 Удалить", self._prof_delete)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            left.addWidget(btn)
        lay.addLayout(left, 0, 0)
        right = QGridLayout()
        lab = QLabel("Название")
        lab.setObjectName("dim")
        right.addWidget(lab, 0, 0)
        self.prof_name = QLineEdit()
        right.addWidget(self.prof_name, 1, 0)
        lab2 = QLabel("Фразы активации (по одной в строке)")
        lab2.setObjectName("dim")
        right.addWidget(lab2, 2, 0)
        self.prof_phrases = QPlainTextEdit()
        self.prof_phrases.setMaximumHeight(70)
        right.addWidget(self.prof_phrases, 3, 0)
        lab3 = QLabel("Действия режима:")
        lab3.setObjectName("dim")
        right.addWidget(lab3, 4, 0)
        self.prof_actions = WorkflowEditor()
        right.addWidget(self.prof_actions, 5, 0)
        save = QPushButton("💾 Сохранить режим")
        save.setObjectName("accent")
        save.clicked.connect(self._prof_save)
        right.addWidget(save, 6, 0)
        lay.addLayout(right, 0, 1)
        lay.setColumnStretch(1, 2)
        self._fill_prof_list()

    def _fill_prof_list(self):
        self.prof_list.blockSignals(True)
        self.prof_list.clear()
        for p in self.brain.profiles.all():
            self.prof_list.addItem(f"{p.get('icon', '⚡')} {p.get('name')}")
        self.prof_list.blockSignals(False)
        self._fill_profiles_combo()

    def _fill_profiles_combo(self):
        self.profile_combo.clear()
        for p in self.brain.profiles.all():
            self.profile_combo.addItem(f"{p.get('icon', '⚡')} {p.get('name')}", p.get("name"))

    def _prof_selected(self, row):
        if row < 0:
            return
        text = self.prof_list.item(row).text()
        name = text.split(" ", 1)[-1]
        prof = next((p for p in self.brain.profiles.all() if p.get("name") == name), None)
        if not prof:
            return
        self.prof_name.setText(prof.get("name", ""))
        self.prof_phrases.setPlainText("\n".join(prof.get("phrases", [])))
        self.prof_actions.set_actions(prof.get("actions", []))

    def _prof_new(self):
        self.prof_list.setCurrentRow(-1)
        self.prof_name.clear()
        self.prof_phrases.clear()
        self.prof_actions.set_actions([])

    def _prof_save(self):
        name = self.prof_name.text().strip()
        if not name:
            self._chat_line("error", "Укажите название режима.")
            return
        prof = {
            "name": name,
            "icon": "⚡",
            "phrases": [p.strip() for p in self.prof_phrases.toPlainText().splitlines()
                        if p.strip()],
            "actions": self.prof_actions.get_actions(),
        }
        if not prof["actions"]:
            self._chat_line("error", "Добавьте хотя бы одно действие.")
            return
        self.brain.profiles.upsert(prof)
        self._fill_prof_list()
        self._chat_line("system", f"Режим «{name}» сохранён.")

    def _prof_delete(self):
        row = self.prof_list.currentRow()
        if row < 0:
            return
        name = self.prof_list.item(row).text().split(" ", 1)[-1]
        self.brain.profiles.delete(name)
        self._fill_prof_list()
        self._prof_new()

    def _run_profile_combo(self):
        name = self.profile_combo.currentData()
        if not name:
            return
        prof = next((p for p in self.brain.profiles.all() if p.get("name") == name), None)
        if prof:
            self.brain.handle(f"режим {name}", "text")

    # ------------------- память -------------------
    # ------------------- разрешения -------------------
    def _build_perms(self, tab):
        from .permissions import CATEGORIES, LEVEL_TITLES
        lay = QVBoxLayout(tab)
        top = QHBoxLayout()
        top.addWidget(QLabel("Уровень доступа:"))
        self.perm_level = QComboBox()
        for key, title in LEVEL_TITLES.items():
            self.perm_level.addItem(title, key)
        self.perm_level.setCurrentIndex(
            list(LEVEL_TITLES).index(self.brain.permissions.level))
        self.perm_level.currentIndexChanged.connect(self._perm_level_changed)
        top.addWidget(self.perm_level)
        top.addStretch(1)
        lay.addLayout(top)
        grid = QGridLayout()
        self.perm_combos = {}
        for i, (cat, title) in enumerate(CATEGORIES):
            grid.addWidget(QLabel(title), i // 2, (i % 2) * 2)
            combo = QComboBox()
            combo.addItem("🟢 разрешить", "allow")
            combo.addItem("🟡 спрашивать", "confirm")
            combo.addItem("🔴 запрещено", "deny")
            current = self.brain.permissions.gate(cat)
            combo.setCurrentIndex({"allow": 0, "confirm": 1, "deny": 2}[current])
            combo.currentIndexChanged.connect(self._perm_changed)
            self.perm_combos[cat] = combo
            grid.addWidget(combo, i // 2, (i % 2) * 2 + 1)
        lay.addLayout(grid)
        note = QLabel("GOD MODE даёт полный контроль без подтверждений. "
                      "Используйте осознанно.")
        note.setObjectName("dim")
        lay.addWidget(note)
        lay.addStretch(1)

    def _perm_level_changed(self):
        from .permissions import LEVELS
        level = self.perm_level.currentData()
        self.brain.permissions.set_level(level)
        for cat, combo in self.perm_combos.items():
            mode = LEVELS[level].get(cat, "deny")
            combo.setCurrentIndex({"allow": 0, "confirm": 1, "deny": 2}[mode])
        self._refresh_perm_badge()
        self._chat_line("system",
                        f"Уровень разрешений: {level.upper()}")

    def _perm_changed(self):
        for cat, combo in self.perm_combos.items():
            self.brain.permissions.set_override(cat, combo.currentData())
        self._refresh_perm_badge()

    def _refresh_perm_badge(self):
        lvl = self.brain.permissions.level
        icons = {"safe": "🛡 SAFE", "normal": "⚙ NORMAL", "god": "⚡ GOD MODE"}
        self.perm_badge.setText(icons.get(lvl, lvl))

    # ------------------- настройки -------------------
    def _build_settings(self, tab):
        c = self.config_obj
        outer = QVBoxLayout(tab)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll_area)
        form_widget = QWidget()
        scroll_area.setWidget(form_widget)
        form = QVBoxLayout(form_widget)
        form.setSpacing(6)
        self.set_vars = {}

        def group(title, checkable=False, checked=True):
            g = QGroupBox(title)
            g.setCheckable(checkable)
            g.setChecked(checked)
            gl = QFormLayout(g)
            form.addWidget(g)
            return gl

        def add_str(g, title, key, password=False, width=300):
            e = QLineEdit(str(c.get(key, "") or ""))
            if password:
                e.setEchoMode(QLineEdit.Password)
            e.setFixedWidth(width)
            g.addRow(title, e)
            self.set_vars[key] = e
            return e

        def add_bool(g, title, key):
            cb = QCheckBox(title)
            cb.setChecked(bool(c.get(key)))
            g.addRow(cb)
            self.set_vars[key] = cb

        def add_combo(g, title, key, values):
            cb = QComboBox()
            cb.addItems(values)
            cur = str(c.get(key, "") or (values[0] if values else ""))
            i = cb.findText(cur)
            if i >= 0:
                cb.setCurrentIndex(i)
            g.addRow(title, cb)
            self.set_vars[key] = cb

        def add_slider(g, title, key, lo, hi):
            row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(lo, hi)
            slider.setValue(int(float(c.get(key, lo))))
            lbl = QLabel(str(slider.value()))
            lbl.setFixedWidth(40)
            slider.valueChanged.connect(lbl.setNum)
            row.addWidget(slider, 1)
            row.addWidget(lbl)
            g.addRow(title, row)
            self.set_vars[key] = slider

        # --- Персона ---
        g1 = group("👤 Персона")
        add_str(g1, "Как меня называть", "user_name", width=160)
        add_str(g1, "Город для погоды", "city", width=160)
        add_combo(g1, "Характер речи", "personality",
                  ["friendly", "professional", "jarvis", "anime"])
        add_slider(g1, "Засыпать после (минут тишины)", "sleep_after_min", 1, 60)

        # --- Голос ---
        g2 = group("🗣 Голос")
        add_bool(g2, "Озвучивать ответы", "tts_enabled")
        add_slider(g2, "Скорость речи", "tts_rate", 100, 260)
        add_slider(g2, "Громкость речи", "tts_volume", 0, 100)
        _voices = self.voice.available_voices()
        self.voice_names = ["По умолчанию"] + [n for _, n in _voices]
        self.voice_ids = [""] + [i for i, _ in _voices]
        cb = QComboBox()
        cb.addItems(self.voice_names)
        cur = c.get("tts_voice_id", "")
        if cur in self.voice_ids:
            cb.setCurrentIndex(self.voice_ids.index(cur))
        g2.addRow("Голос системы", cb)
        self.voice_combo = cb
        test = QPushButton("🔊 Тест голоса")
        test.clicked.connect(lambda: self.voice.say(
            "Привет! Я Аврора. Проверка голоса завершена."))
        g2.addRow(test)

        # --- Голосовое управление ---
        g3 = group("👂 Голосовое управление")
        add_str(g3, "Кодовое слово", "wake_word", width=140)
        add_bool(g3, "Требовать кодовое слово перед командой", "require_wake_word")
        add_bool(g3, "Клавиша Ctrl+Space — говорить из любого места", "hotkey_enabled")
        mic_hint = QLabel("Микрофон включается кнопкой 🎙 в шапке окна.")
        mic_hint.setObjectName("dim")
        g3.addRow(mic_hint)
        hk_hint = QLabel("Быстрые запуски (Ctrl+1…4): имя из «быстрых запусков» ниже.")
        hk_hint.setObjectName("dim")
        g3.addRow(hk_hint)
        self.hotkey_edits = {}
        qk = list((c.get("quick_launch") or {}).keys())
        for combo in ("ctrl+1", "ctrl+2", "ctrl+3", "ctrl+4"):
            e = QLineEdit(str((c.get("hotkeys") or {}).get(combo, "")))
            e.setFixedWidth(140)
            box = QHBoxLayout()
            box.addWidget(QLabel(combo + " →"))
            combo_names = QComboBox()
            combo_names.addItems(qk)
            if e.text() in qk:
                combo_names.setCurrentText(e.text())
            combo_names.currentTextChanged.connect(e.setText)
            box.addWidget(combo_names)
            row = QWidget()
            row.setLayout(box)
            g3.addRow(row)
            self.hotkey_edits[combo] = e

        # --- Нейросеть ---
        g4 = group("🤖 Нейросеть")
        add_bool(g4, "Включить ИИ (отвечает, когда не поняла команду)", "ai_enabled")
        add_str(g4, "Base URL", "ai_base_url", width=340)
        add_str(g4, "API-ключ", "ai_api_key", password=True, width=340)
        add_str(g4, "Модель", "ai_model", width=200)
        add_bool(g4, "ИИ может выполнять действия на ПК", "ai_allow_actions")
        add_bool(g4, "Зрение: анализ экрана по запросу", "vision_enabled")
        test_ai = QPushButton("📡 Проверить связь")
        test_ai.clicked.connect(self._test_ai)
        g4.addRow(test_ai)

        # --- Память ---
        g5 = group("🧠 Память")
        mem_hint = QLabel("Скажите «запомни: …» — или впишите факты тут, по одному в строке.")
        mem_hint.setObjectName("dim")
        g5.addRow(mem_hint)
        self.facts_edit = QPlainTextEdit()
        self.facts_edit.setMaximumHeight(90)
        self.facts_edit.setPlainText("\n".join(self.brain.memory.facts))
        g5.addRow(self.facts_edit)

        # --- Продвинутые (свёрнуты по умолчанию) ---
        g6 = group("🔧 Продвинутые настройки (редко нужны)", checkable=True, checked=False)
        add_combo(g6, "Язык распознавания", "language",
                  ["ru-RU", "en-US", "uk-UA", "de-DE", "fr-FR", "es-ES"])
        add_combo(g6, "Движок распознавания", "stt_engine", ["google", "vosk"])
        add_str(g6, "Путь к модели Vosk (офлайн)", "vosk_model_path", width=340)
        add_str(g6, "Vision-модель (пусто = основная)", "vision_model", width=200)
        add_str(g6, "Ссылка «включи музыку»", "music_url", width=340)
        add_str(g6, "Папка для скриншотов", "screenshots_dir", width=340)
        add_bool(g6, "Подтверждать выключение ПК", "confirm_power")
        add_bool(g6, "Горячие клавиши Ctrl+1…4 включены", "hotkeys_enabled")
        add_str(g6, "Путь к программе заметок (ту ду лист)", "notes_app", width=340)
        for qk_key in ("dev", "krita", "unity", "blender"):
            add_str(g6, f"Быстрый запуск «{qk_key}»", "quick_launch/" + qk_key, width=340)
        self.projects_folder_edit = QLineEdit(
            str(self.brain.memory.get_pref("projects_folder", "")))
        self.projects_folder_edit.setFixedWidth(340)
        g6.addRow("Папка проектов", self.projects_folder_edit)

        save = QPushButton("💾 СОХРАНИТЬ НАСТРОЙКИ")
        save.setObjectName("accent")
        save.clicked.connect(self._save_settings)
        form.addWidget(save)
        form.addStretch(1)

    # ==================================================================
    # действия интерфейса
    # ==================================================================
    def _bootstrap(self):
        self._chat_line("system", "AURA запущена. Введите команду или включите микрофон.")
        if self.mic_btn.isChecked():
            self._toggle_mic(True)

    def _toggle_mic(self, on):
        if self.ear is None:
            self._chat_line("error", "Микрофон недоступен (компонент не инициализирован).")
            return
        if on:
            ok = self.ear.start()
            self._chat_line("system", "Микрофон включается…" if ok else
                            "Микрофон недоступен — работаем с клавиатуры.")
        else:
            self.ear.stop()
            self.mic_active = False
            self.face.set_state("sleep")
            self._set_status("Микрофон выключен", "off")
            self._chat_line("system", "Микрофон выключен.")

    def _push_talk(self):
        if not self.ear.listen_once():
            self._chat_line("error", "Микрофон недоступен. Проверьте PyAudio/устройство.")
        else:
            self._set_status("Слушаю…", "listening")

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.brain.handle(text, "text")

    def _vision(self):
        self.brain.handle("что у меня на экране", "text")

    def _teach(self):
        if self.recorder is None or not self.recorder.available:
            self._chat_line("error",
                            "Teach Mode требует пакет pynput: pip install pynput")
            return
        if not self._recording:
            if self.recorder.start():
                self._recording = True
                self.sender().setText("⏹ Стоп записи")
        else:
            actions = self.recorder.stop()
            self._recording = False
            self.sender().setText("⏺ Учить")
            if actions:
                name, ok = QInputDialog.getText(
                    self, "Новая команда",
                    f"Записано {len(actions)} действий.\nНазвание команды:")
                if ok and name.strip():
                    self.brain.custom.upsert({
                        "name": name.strip(),
                        "phrases": [name.strip().lower()],
                        "actions": actions,
                    })
                    self._fill_cmd_list()
                    self.tabs.setCurrentIndex(2)
                    self._chat_line("system",
                                    f"Команда «{name.strip()}» создана из записи.")

    def _test_ai(self):
        self._apply_settings()
        self.config_obj.save()

        def run():
            try:
                reply = self.brain.ai.test_connection()
                self.events.put({"kind": "log", "level": "system",
                                 "msg": f"ИИ отвечает: «{reply}» — связь есть ✅"})
            except Exception as exc:
                self.events.put({"kind": "log", "level": "error",
                                 "msg": f"ИИ не отвечает: {exc}"})
        import threading
        threading.Thread(target=run, daemon=True).start()
        self._chat_line("system", "Проверяю связь с ИИ…")

    def _apply_settings(self):
        c = self.config_obj
        v = self.set_vars
        for key, w in v.items():
            if isinstance(w, QCheckBox):
                c.set(key, bool(w.isChecked()))
            elif isinstance(w, QComboBox):
                c.set(key, w.currentText())
            elif isinstance(w, QSlider):
                val = w.value()
                c.set(key, val if key != "tts_volume" else val / 100.0)
            elif isinstance(w, QLineEdit):
                if "/" in key:
                    sect, sub = key.split("/", 1)
                    merged = dict(c.get(sect) or {})
                    merged[sub] = w.text().strip()
                    c.set(sect, merged)
                else:
                    c.set(key, w.text().strip())
        hk = {}
        for combo, e in getattr(self, "hotkey_edits", {}).items():
            if e.text().strip():
                hk[combo] = e.text().strip()
        if hk:
            c.set("hotkeys", hk)
        idx = self.voice_combo.currentIndex()
        c.set("tts_voice_id", self.voice_ids[idx] if idx >= 0 else "")
        if getattr(self, "projects_folder_edit", None) is not None:
            self.brain.memory.set_pref("projects_folder",
                                       self.projects_folder_edit.text().strip())

    def _save_settings(self):
        self._apply_settings()
        self.brain.memory.facts = [x.strip()
                                   for x in self.facts_edit.toPlainText().splitlines()
                                   if x.strip()]
        self.brain.memory.save()
        self.config_obj.save()
        if self.hotkeys is not None and self.hotkeys.available:
            self.hotkeys.restart()
            self._chat_line("system", "Настройки сохранены ✓ Горячие клавиши обновлены.")
        else:
            self._chat_line("system", "Настройки сохранены ✓")

    # ==================================================================
    # события фоновых потоков
    # ==================================================================
    def _poll_events(self):
        try:
            while True:
                evt = self.events.get_nowait()
                try:
                    self._handle_event(evt)
                except Exception:
                    pass
        except queue.Empty:
            pass

    def _handle_event(self, evt):
        kind = evt.get("kind")
        if kind == "log":
            level = evt.get("level", "system")
            self._chat_line(level, evt.get("msg", ""))
        elif kind == "state":
            name = evt["name"]
            self.face.set_state(name)
            self._set_status(evt.get("label") or STATE_LABELS.get(name, ""), name)
        elif kind == "heard":
            self.subtitle.setText(f"Вы: {evt['text']}")
        elif kind == "say_start":
            self.face.set_state("speaking")
            self._set_status("Говорю…", "speaking")
            self._chat_line("aura", evt.get("text", ""))
            self.subtitle.setText(f"AURA: {evt.get('text', '')[:120]}")
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
        elif kind == "activity":
            icon = evt.get("icon", "•")
            item = QTreeWidgetItem([evt.get("time", ""), f"{icon} {evt.get('desc', '')}",
                                    "↶" if evt.get("has_undo") else ""])
            self.activity_tree.insertTopLevelItem(0, item)
        elif kind == "mood":
            mood = evt.get("mood", "neutral")
            emoji = MOOD_EMOJI.get(mood, "😐")
            names = {"neutral": "нейтрально", "happy": "довольна",
                     "curious": "любопытно", "sleepy": "сонно",
                     "annoyed": "раздражено", "confident": "уверенно",
                     "concerned": "обеспокоена"}
            self.mood_label.setText(f"{emoji} {names.get(mood, mood)}")
            self.energy.setValue(int(evt.get("energy", 87)))
            self.face.set_mood(mood, evt.get("energy", 87))
            if mood == "sleepy":
                self.face.set_state("sleep")
            elif mood != "sleepy" and self.face._state == "sleep":
                self.face.set_state("listening" if self.mic_active else "idle")

    def _set_status(self, text, state="idle"):
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f"color: {STATE_COLORS_UI.get(state, FG_DIM)};")
        self.dot.setStyleSheet(f"color: {STATE_COLORS_UI.get(state, FG_DIM)};")
        self.status.setText(text)

    # ==================================================================
    def closeEvent(self, evt):
        try:
            if self.hotkeys:
                self.hotkeys.stop()
            if self.recorder and self.recorder.recording:
                self.recorder.stop()
            self.face.stop()
            if self.ear is not None:
                self.ear.stop()
            if self.voice is not None:
                self.voice.shutdown()
        finally:
            super().closeEvent(evt)
