# -*- coding: utf-8 -*-
"""Мозг ассистента: принимает текст (с голоса или печатный) и решает, что делать.

Порядок обработки:
  1. подтверждение питания (да/нет после «выключи компьютер»);
  2. встроенные навыки фазы 1;
  3. пользовательские команды из JSON;
  4. встроенный навык «открой …» (фаза 2);
  5. ИИ (если включён) — ответ + возможные действия;
  6. «не понял».
"""
import datetime
import re
import threading
from collections import deque

from .ai import AIClient, SYSTEM_PROMPT, ACTIONS_PROMPT
from .skills.actions import ActionContext, execute_actions
from .skills.builtins import SkillContext, get_skills
from .skills.custom import CustomCommands

FORGET_MARKER = "__FORGET_HISTORY__"


class Brain:
    def __init__(self, config, voice, emit, ear=None):
        self.config = config
        self.voice = voice
        self.emit = emit
        self.ear = ear
        self.ai = AIClient(config, emit)
        self.custom = CustomCommands(emit=emit)
        self.skills = get_skills()
        self.history = deque(maxlen=int(config.get("ai_history_limit", 8)) * 2)
        self._pending_confirm = None      # (prompt, callback, expires_at)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def say(self, text: str):
        if text:
            self.voice.say(text)

    def _log(self, msg, level="system"):
        self.emit("log", level=level, msg=msg)

    # ------------------------------------------------------------------
    def handle(self, text: str, source: str = "voice"):
        """Публичный вход: текст пользователя. Обрабатывается в фоне."""
        threading.Thread(target=self._process, args=(text, source),
                         name="brain", daemon=True).start()

    def _process(self, text: str, source: str):
        text = (text or "").strip()
        if not text:
            return
        self._log(f"{'🎤' if source == 'voice' else '⌨'} {text}", level="user")
        norm = CustomCommands.normalize(text)

        with self._lock:
            if self._handle_confirmation(norm):
                return

        self.emit("state", name="thinking", label="Думаю…")

        # 2. встроенные навыки (фаза 1)
        for skill in self.skills:
            if skill.phase != 1:
                continue
            for pat in skill.patterns:
                m = pat.search(norm)
                if m:
                    self._run_skill(skill, norm, m)
                    return

        # 3. пользовательские команды
        cmd, reply = self.custom.match(text)
        if cmd is not None:
            self._run_custom(cmd, reply)
            return

        # 4. «открой …» (фаза 2)
        for skill in self.skills:
            if skill.phase != 2:
                continue
            for pat in skill.patterns:
                m = pat.search(norm)
                if m:
                    self._run_skill(skill, norm, m)
                    return

        # 5. ИИ
        if self.ai.ready:
            self._ask_ai(text)
            return

        self.emit("state", name="idle", label="Ожидаю…")
        self.say("Команда не распознана. Подключите ИИ в настройках или добавьте "
                 "свою команду во вкладке «Команды».")

    # ------------------------------------------------------------------
    def _run_skill(self, skill, norm, m):
        action_ctx = ActionContext(say=self.say, log=self._log, config=self.config)
        ctx = SkillContext(say=self.say, log=self._log, config=self.config,
                           action_ctx=action_ctx, ear=self.ear, voice=self.voice)
        try:
            reply = skill.handler(norm, m, ctx)
        except Exception as exc:
            self._log(f"Ошибка навыка «{skill.name}»: {exc}", level="error")
            self.emit("state", name="alert", label="Ошибка")
            reply = "Что-то пошло не так при выполнении команды."
        if reply == FORGET_MARKER:
            self.history.clear()
            reply = "История диалога очищена."
        if ctx.pending_confirm:
            prompt, fn = ctx.pending_confirm
            self._pending_confirm = (prompt, fn, datetime.datetime.now().timestamp() + 25)
            self.say(prompt + " Скажите «да» или «нет».")
            self.emit("state", name="listening", label="Жду подтверждения…")
            return
        self._finish(reply)

    def _run_custom(self, cmd, reply):
        name = cmd.get("name", "?")
        self._log(f"Своя команда: «{name}»")
        action_ctx = ActionContext(say=self.say, log=self._log, config=self.config)
        ok = execute_actions(cmd.get("actions", []), action_ctx)
        self.emit("state", name="idle", label=f"Выполнила: {name}")
        spoken = (reply or "").strip()
        if not spoken:
            says = [a.get("text", "") for a in cmd.get("actions", [])
                    if isinstance(a, dict) and a.get("type") == "say"]
            spoken = says[0] if says else (f"Выполнила «{name}»" if ok else "")
        self.say(spoken)

    # ------------------------------------------------------------------
    def _ask_ai(self, text: str):
        allow = bool(self.config.get("ai_allow_actions"))
        system = SYSTEM_PROMPT + (ACTIONS_PROMPT if allow else
                                  " У тебя нет доступа к компьютеру пользователя.")
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": text})
        self._log("Запрос к ИИ…")
        try:
            reply = self.ai.chat(messages)
        except Exception as exc:
            self._log(f"Ошибка ИИ: {exc}", level="error")
            self.emit("state", name="alert", label="ИИ недоступен")
            self.say("Не удалось связаться с нейросетью. Проверьте настройки ИИ.")
            return
        clean, actions = AIClient.parse_reply(reply or "")
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": clean})
        if actions and allow:
            action_ctx = ActionContext(say=self.say, log=self._log, config=self.config)
            execute_actions(actions, action_ctx)
        self.emit("state", name="idle", label="Ожидаю…")
        self.say(clean)

    # ------------------------------------------------------------------
    def _handle_confirmation(self, norm: str) -> bool:
        if not self._pending_confirm:
            return False
        prompt, fn, expires = self._pending_confirm
        if datetime.datetime.now().timestamp() > expires:
            self._pending_confirm = None
            self.say("Время подтверждения истекло, отмена.")
            return True
        if re.match(r"^(да|подтвержда\w*|давай|ага|ну да|yes|окей|ок)\W*$", norm):
            self._pending_confirm = None
            self.emit("state", name="thinking", label="Выполняю…")
            threading.Thread(target=fn, daemon=True).start()
            self.say("Выполняю.")
            return True
        if re.match(r"^(нет|не|отмена|отмен\w*|стоп|не надо|no)\W*$", norm):
            self._pending_confirm = None
            self.emit("state", name="idle", label="Отменено")
            self.say("Отмена.")
            return True
        return False

    # ------------------------------------------------------------------
    def _finish(self, reply):
        self.emit("state", name="idle", label="Ожидаю…")
        self.say(reply)

    def shutdown(self):
        pass
