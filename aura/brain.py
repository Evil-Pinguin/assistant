# -*- coding: utf-8 -*-
"""Мозг AURA: текст → понимание → безопасное действие → ответ.

Порядок обработки:
  1. подтверждения («да/нет» после вопроса ассистента);
  2. настроение: ловим фрустрацию пользователя;
  3. зрение: «что на экране», «нажми на …»;
  4. встроенные навыки (фаза 1);
  5. режимы (профили);
  6. пользовательские команды;
  7. «открой …» (фаза 2);
  8. ИИ (если включён) — ответ + предлагаемые действия через Tool Router;
  9. «не понял».

Все действия проходят через Permissions и попадают в Центр активности (undo).
"""
import datetime
import random
import re
import threading
from collections import deque

from .ai import AIClient, SYSTEM_PROMPT, ACTIONS_PROMPT, PERSONALITY_STYLES
from .mood import MoodEngine
from .memory import Memory
from .permissions import Permissions
from .activity import Activity
from .profiles import Profiles
from . import vision as V
from .skills import actions as A
from .skills.builtins import SkillContext, get_skills
from .skills.custom import CustomCommands

FORGET_MARKER = "__FORGET_HISTORY__"

PERSONALITY_ACKS = {
    "professional": ("Команда выполнена.", "Готово.", "Сделано."),
    "friendly": ("Готово!", "Всё сделала!", "Есть!"),
    "jarvis": ("Разумеется.", "Как пожелаете.", "Будет исполнено."),
    "anime": ("Есть~ Выполняю!", "Окэй~, готово!", "Хай-хай! Сделано!"),
}

ACTION_START_RE = re.compile(
    r"^(Открываю|Запускаю|Включаю|Ищу|Делаю|Ставлю|Сворачиваю|Блокирую|Выключаю|"
    r"Перезагружаю|Создала|Нашла|Закрываю|Вставила|Архив)")


class Brain:
    def __init__(self, config, voice, emit, ear=None):
        self.config = config
        self.voice = voice
        self.emit = emit
        self.ear = ear
        self.ai = AIClient(config, emit)
        self.permissions = Permissions(config)
        self.memory = Memory(emit=emit)
        self.activity = Activity(emit=emit)
        self.mood = MoodEngine(config, emit)
        self.custom = CustomCommands(emit=emit)
        self.profiles = Profiles(emit=emit)
        self.skills = get_skills()
        self.history = deque(maxlen=int(config.get("ai_history_limit", 8)) * 2)
        self._pending_confirm = None   # (prompt, fn, expires)
        self._confirm_lock = threading.Lock()
        self._last_reply_time = 0

    # ------------------------------------------------------------------
    def say(self, text):
        if text:
            self.voice.say(text)

    def _log(self, msg, level="system"):
        self.emit("log", level=level, msg=msg)

    def personality_ack(self):
        acks = PERSONALITY_ACKS.get(self.config.get("personality", "friendly"))
        return random.choice(acks) if acks else ""

    # ------------------------------------------------------------------
    def handle(self, text, source="voice"):
        threading.Thread(target=self._process, args=(text, source),
                         name="aura-brain", daemon=True).start()

    def _process(self, text, source):
        text = (text or "").strip()
        if not text:
            return
        self._log(f"{'🎤' if source == 'voice' else '⌨'} {text}", level="user")
        norm = CustomCommands.normalize(text)

        with self._confirm_lock:
            if self._handle_confirmation(norm):
                return

        frustrated = self.mood.observe_user(text)
        self.emit("state", name="thinking", label="Думаю…")

        # 1) встроенные навыки
        from .skills.builtins import NO_MATCH
        for skill in self.skills:
            if skill.phase != 1:
                continue
            for pat in skill.patterns:
                m = pat.search(norm)
                if m:
                    reply = self._run_skill(skill, norm, m)
                    if reply == NO_MATCH:
                        continue
                    self._finish(reply, frustrated)
                    return

        # 2) режимы
        prof = self.profiles.match(norm)
        if prof:
            self._run_profile(prof)
            return

        # 3) пользовательские команды
        cmd, reply = self.custom.match(text)
        if cmd is not None:
            self._run_custom(cmd, reply, frustrated)
            return

        # 4) «открой …»
        for skill in self.skills:
            if skill.phase != 2:
                continue
            for pat in skill.patterns:
                m = pat.search(norm)
                if m:
                    reply = self._run_skill(skill, norm, m)
                    if reply == NO_MATCH:
                        continue
                    self._finish(reply, frustrated)
                    return

        # 5) ИИ
        if self.ai.ready:
            self._ask_ai(text, frustrated=frustrated)
            return

        self.emit("state", name="idle", label="Ожидаю…")
        self.say("Команда не распознана. Подключите ИИ в настройках или добавьте "
                 "свою команду во вкладке «Команды».")

    # ------------------------------------------------------------------
    def _run_skill(self, skill, norm, m):
        ctx = self._make_ctx()
        try:
            reply = skill.handler(norm, m, ctx)
        except Exception as exc:
            self._log(f"Ошибка навыка «{skill.name}»: {exc}", level="error")
            self.emit("state", name="error", label="Ошибка")
            self.mood.on_error()
            if "пакет" in str(exc):
                return f"Не получилось: {exc}"
            return "Что-то пошло не так при выполнении команды."
        if reply == FORGET_MARKER:
            self.history.clear()
            return "История диалога очищена."
        if ctx.pending_confirm:
            prompt, fn = ctx.pending_confirm
            self._set_pending(prompt, fn)
            return None  # подтверждение спросим отдельно
        self.mood.on_success()
        self.emit("state", name="success", label="Готово")
        return reply

    def _make_ctx(self):
        action_ctx = A.ActionContext(
            say=self.say, log=self._log, config=self.config,
            permissions=self.permissions, activity=self.activity)
        return SkillContext(say=self.say, log=self._log, config=self.config,
                            action_ctx=action_ctx, ear=self.ear, voice=self.voice,
                            brain=self, memory=self.memory)

    # ---------- режимы и пользовательские команды (workflow) ----------
    def _run_workflow(self, actions, label, reply_override="", frustrated=False):
        """Единый конвейер выполнения цепочек действий с разрешениями."""
        actions, dropped = A.strip_denied(actions, self.permissions)
        for d in dropped:
            self._log(f"Действие «{d}» отклонено разрешениями "
                      f"({self.permissions.level.upper()}).", level="error")
        if not actions:
            self.emit("state", name="error", label="Запрещено")
            return "Эти действия запрещены текущим уровнем разрешений."

        needed = A.check_confirm_needed(actions, self.permissions)
        if needed:
            cats = ", ".join(needed)
            self._set_pending(f"Команда «{label}» требует разрешения: {cats}. Выполнить?",
                              lambda: self._execute_chain(actions, label))
            return None

        result = self._execute_chain(actions, label)
        return reply_override or result

    def _execute_chain(self, actions, label):
        action_ctx = A.ActionContext(
            say=self.say, log=self._log, config=self.config,
            permissions=self.permissions, activity=self.activity)
        self.activity.add(f"Режим/команда: {label}", kind="workflow", icon="⚡")
        ok = A.execute_actions(actions, action_ctx)
        self.mood.on_success(count=len(actions))
        self.emit("state", name="success", label=f"Выполнила: {label}")
        return f"Выполнила «{label}»" if ok else ""

    def _run_profile(self, prof):
        self._log(f"Режим: {prof.get('icon', '')} {prof.get('name')}")
        reply = self._run_workflow(prof.get("actions", []),
                                   label=f"режим {prof.get('name')}")
        self._finish(reply)

    def _run_custom(self, cmd, reply, frustrated=False):
        name = cmd.get("name", "?")
        self._log(f"Своя команда: «{name}»")
        says = [a.get("text", "") for a in cmd.get("actions", [])
                if isinstance(a, dict) and a.get("type") == "say"]
        spoken = (reply or "").strip() or (says[0] if says else "")
        result = self._run_workflow(cmd.get("actions", []), label=name)
        self._finish(spoken or result, frustrated)

    # ------------------------------------------------------------------
    def _ask_ai(self, text, frustrated=False, image_bytes=None, force_actions=False):
        allow = bool(self.config.get("ai_allow_actions")) or force_actions
        mood = self.mood.state()
        system = (SYSTEM_PROMPT + " "
                  + PERSONALITY_STYLES.get(self.config.get("personality", "friendly"), ""))
        mem = self.memory.as_prompt()
        if mem:
            system += "\n" + mem
        system += (f"\nТекущее состояние: настроение {mood['mood']}, энергия "
                   f"{mood['energy']}%.")
        if allow:
            system += ACTIONS_PROMPT
        else:
            system += " У тебя нет доступа к компьютеру пользователя."
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history)
        if image_bytes is not None:
            messages.extend(V.vision_messages(text, image_bytes, system=""))
        else:
            messages.append({"role": "user", "content": text})
        self._log("Запрос к ИИ…")
        self.emit("state", name="thinking", label="Думаю…")
        try:
            reply = self.ai.chat(messages, vision=image_bytes is not None)
        except Exception as exc:
            self._log(f"Ошибка ИИ: {exc}", level="error")
            self.emit("state", name="error", label="ИИ недоступен")
            self.mood.on_error()
            self.say("Не удалось связаться с нейросетью. Проверьте настройки ИИ.")
            return
        clean, ai_actions = AIClient.parse_reply(reply or "")
        if image_bytes is None:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": clean})
        if ai_actions and allow:
            self._run_workflow(ai_actions, label="задание ИИ")
            self.emit("state", name="idle", label="Ожидаю…")
            self.say(clean)
            return
        self.emit("state", name="idle", label="Ожидаю…")
        self.say(clean)

    # ------------------------------------------------------------------
    # Зрение
    # ------------------------------------------------------------------
    def vision_analyze(self, question) -> str:
        if not self.config.get("vision_enabled", True):
            return "Зрение отключено в настройках."
        if not self.ai.ready:
            return ("Для зрения нужен ИИ: включите его в настройках "
                    "(любой OpenAI-совместимый API с vision-моделью).")
        shot = V.grab_jpeg()
        if shot is None:
            return "Не удалось сделать скриншот. Нужен пакет Pillow."
        self._log("👁 AURA VISION: анализирую экран…")
        self._ask_ai(question, image_bytes=shot)
        return ""  # ответ придёт голосом из _ask_ai

    def vision_click(self, target) -> str:
        if not self.ai.ready:
            return "Для управления экраном нужен подключённый ИИ."
        shot = V.grab_jpeg()
        if shot is None:
            return "Не удалось сделать скриншот."
        q = (f"На скриншоте найди элемент «{target}». Определи его координаты в пикселях "
             f"относительно изображения. Если нашёл — ответь коротко и добавь блок "
             f"действия click с координатами. Если нет — скажи, что элемент не виден.")
        self._log(f"👁 AURA VISION: ищу «{target}» на экране…")
        self._ask_ai(q, image_bytes=shot, force_actions=True)
        return ""

    # ------------------------------------------------------------------
    # Отмена
    # ------------------------------------------------------------------
    def undo_last_async(self):
        threading.Thread(target=self._undo_sync, daemon=True).start()

    def _undo_sync(self):
        desc = self.activity.undo_last()
        if desc:
            self.emit("state", name="success", label="Отменено")
            self.say(f"Отменила: {desc}")
        else:
            self.emit("state", name="idle", label="Нечего отменять")
            self.say("Не нашла действий, которые можно отменить.")

    # ------------------------------------------------------------------
    # Подтверждения
    # ------------------------------------------------------------------
    def _set_pending(self, prompt, fn):
        self._pending_confirm = (prompt, fn,
                                 datetime.datetime.now().timestamp() + 60)
        self.say(prompt + " Скажите «да» или «нет».")
        self.emit("state", name="listening", label="Жду подтверждения…")
        self.activity.add(f"Жду подтверждения: {prompt}", kind="confirm", icon="❓")

    def _handle_confirmation(self, norm) -> bool:
        if not self._pending_confirm:
            return False
        prompt, fn, expires = self._pending_confirm
        if datetime.datetime.now().timestamp() > expires:
            self._pending_confirm = None
            self.say("Время подтверждения истекло, отмена.")
            return True
        if re.match(r"^(да|подтвержда\w*|давай|ага|ну да|yes|окей|ок|конечно)\W*$", norm):
            self._pending_confirm = None
            self.emit("state", name="thinking", label="Выполняю…")
            self.say(self.personality_ack() or "Выполняю.")
            threading.Thread(target=self._safe_call, args=(fn,), daemon=True).start()
            return True
        if re.match(r"^(нет|не|отмена|отмен\w*|стоп|не надо|no)\W*$", norm):
            self._pending_confirm = None
            self.emit("state", name="idle", label="Отменено")
            self.say("Отмена.")
            return True
        return False

    @staticmethod
    def _safe_call(fn):
        try:
            fn()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _finish(self, reply, frustrated=False):
        if reply is None:
            return
        reply = (reply or "").strip()
        prefix = ""
        if frustrated:
            prefix = self.mood.empathy_line() + " "
        elif reply and ACTION_START_RE.match(reply) and random.random() < 0.45:
            ack = self.personality_ack()
            if ack:
                prefix = ack + " "
        self.emit("state", name="idle", label="Ожидаю…")
        self.say(prefix + reply)

    def shutdown(self):
        pass
