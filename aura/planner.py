# -*- coding: utf-8 -*-
"""Planner: намерение → план → подтверждение → выполнение → проверка.

План — это список шагов. Шаг — либо готовые action-дикты (плейбук),
либо вложенная команда (фраза, которую мозг проведёт как обычную).
Ничего не выполняется без подтверждения, если шагов больше одного,
и никогда не выполняется вслепую.

Источники планов:
  * «сделай как вчера»        — журнал контекста → шаги прошлой сессии;
  * «подготовь к работе»      — профиль «Работа» из настроек или шаблон;
  * «открой X, потом Y»       — последовательность вложенных команд.
"""
import datetime
import re

SEQ_SPLIT_RE = re.compile(
    r"\s+(?:и\s+потом|а\s+потом|а\s+затем|потом|затем|после\s+этого)\s+",
    re.IGNORECASE)
LIKE_YESTERDAY_RE = re.compile(
    r"(?:сделай|повтори|верни|запусти|открой)\s+(?:всё\s+)?как\s+вчера"
    r"|(?:сделай|повтори|верни)\s+вчерашн\w+")
START_WORK_RE = re.compile(
    r"подготов\w*\s+(?:компьютер|пк|систему|всё|все)?\s*(?:к\s+работе|рабоч\w+)"
    r"|собери\s+рабоч\w+|организуй\s+работу|начать\s+работу|рабочий\s+сценарий")

WORK_PROFILE_HINT = "работ"
DEFAULT_WORK_APPS = ["код", "браузер"]

_ACTION_VERBS = {
    "open_app": "Открыть", "open": "Открыть", "app": "Открыть",
    "open_url": "Открыть ссылку", "url": "Открыть ссылку",
    "open_file": "Открыть файл", "volume": "Громкость",
    "press": "Нажать", "type_text": "Напечатать", "close_app": "Закрыть",
    "wait": "Пауза", "say": "Сказать",
}


def split_sequence(norm):
    """«открой код потом браузер» → ["открой код", "браузер"] (или [])."""
    parts = [p.strip(" ,.") for p in SEQ_SPLIT_RE.split(norm or "")]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else []


def describe_action(a):
    """Человекочитаемое описание action-дикта."""
    if not isinstance(a, dict):
        return str(a)
    t = a.get("type", "?")
    target = str(a.get("target") or a.get("text") or "").strip()
    verb = _ACTION_VERBS.get(t, t)
    return f"{verb} {target}".strip()


class Step:
    def __init__(self, desc, actions=None, command=None):
        self.desc = desc
        self.actions = actions      # list[dict] — плейбук
        self.command = command      # str — вложенная команда


class Plan:
    def __init__(self, title, steps, source="template", started=None):
        self.title = title
        self.steps = steps
        self.source = source        # template | history | sequence
        self.started = started      # ts начала (для «как вчера»)

    def prompt(self):
        lines = [f"{i}. {s.desc}" for i, s in enumerate(self.steps, 1)]
        return f"План «{self.title}»:\n" + "\n".join(lines)


class Planner:
    def __init__(self):
        self.last_reason = ""       # почему план не собран (для реплики)

    def match(self, norm, context=None, profiles=None, config=None):
        """→ Plan | None. Пустой steps = намерение понято, но данных нет."""
        if LIKE_YESTERDAY_RE.search(norm):
            session = context.find_past_session() if context else None
            if not session:
                self.last_reason = "no-history"
                return Plan("Как вчера", [], source="history")
            steps = [Step(e.get("desc", "?"), actions=e.get("actions"))
                     for e in session["steps"]]
            when = datetime.datetime.fromtimestamp(session["started"])
            return Plan(f"Как вчера ({when.strftime('%H:%M')})", steps,
                        source="history", started=session["started"])
        if START_WORK_RE.search(norm):
            return self._start_work(profiles, config)
        return None

    def _start_work(self, profiles, config):
        profile = None
        try:
            items = profiles.all() if profiles is not None and hasattr(
                profiles, "all") else list(profiles or [])
        except Exception:
            items = []
        for p in items:
            blob = (p.get("name", "") + " " + " ".join(p.get("phrases", []))).lower()
            if WORK_PROFILE_HINT in blob:
                profile = p
                break
        if profile:
            steps = []
            for a in profile.get("actions", []):
                if isinstance(a, dict) and a.get("type") == "say":
                    continue
                steps.append(Step(describe_action(a), actions=[a]))
            return Plan(f"Режим «{profile.get('name', 'работа')}»", steps,
                        source="template")
        apps = None
        try:
            apps = config.get("work_apps") if config is not None else None
        except Exception:
            apps = None
        steps = [Step(f"Открыть {a}", command=f"открой {a}")
                 for a in (apps or DEFAULT_WORK_APPS)]
        return Plan("Рабочее место", steps, source="template")
