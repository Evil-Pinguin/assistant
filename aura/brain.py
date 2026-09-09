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
from .context import ContextEngine
from .planner import Plan, Planner, Step, describe_action, split_sequence
from .profiles import Profiles
from .state import StateMachine
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
        self.state = StateMachine(emit)
        self.context = ContextEngine(emit, config)
        self.context.on_alert = self._on_proactive
        self.planner = Planner()
        self._pending_choice = None    # (options[(label, fn)], expires)
        if config.get("context_monitor", True):
            self.context.start_monitor()

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

    def _process(self, text, source="voice", depth=0):
        text = (text or "").strip()
        if not text:
            return
        self._log(f"{'🎤' if source == 'voice' else '⌨'} {text}", level="user")
        norm = CustomCommands.normalize(text)

        with self._confirm_lock:
            if self._handle_confirmation(norm):
                return

        frustrated = self.mood.observe_user(text)
        self.state.set("processing")
        self.emit("think", text="АНАЛИЗИРУЮ ЗАПРОС")

        # 0) последовательность: «открой X, потом Y» → план
        if depth == 0:
            parts = split_sequence(norm)
            if parts:
                self._offer_plan(Plan("Последовательность",
                                      [Step(desc=p, command=p) for p in parts],
                                      source="sequence"), frustrated)
                return

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

        # 2.5) планировщик: «как вчера», «подготовь компьютер к работе»
        if depth == 0:
            plan = self.planner.match(norm, context=self.context,
                                      profiles=self.profiles, config=self.config)
            if plan is not None:
                self._offer_plan(plan, frustrated)
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

        self.state.set("idle")
        self.say("Команда не распознана. Подключите ИИ в настройках или добавьте "
                 "свою команду во вкладке «Команды».")

    # ------------------------------------------------------------------
    def _run_skill(self, skill, norm, m):
        ctx = self._make_ctx()
        try:
            reply = skill.handler(norm, m, ctx)
        except Exception as exc:
            self._log(f"Ошибка навыка «{skill.name}»: {exc}", level="error")
            self.state.set("error")
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
        self.state.set("success")
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
            self.state.set("error")
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
        self.activity.add(f"Задача: {label}", kind="workflow", icon="⚡")
        real = [a for a in (actions or [])
                if not (isinstance(a, dict) and a.get("type") == "say")]
        if real:
            self.context.note("workflow", label, actions=real)
        self.state.set("executing")

        def _step(i, n, action):
            self.emit("think",
                      text=f"ШАГ {i}/{n} · {describe_action(action).upper()}")

        ok, failed = A.execute_actions(actions, action_ctx, on_step=_step)
        self.emit("think", text="")
        if ok and not failed:
            self.state.set("verifying")
            self.emit("think", text="ПРОВЕРЯЮ РЕЗУЛЬТАТ")
            self.mood.on_success(count=ok)
            self.state.set("success")
            self.emit("think", text="")
            return f"Готово: {label}."
        if ok:
            self.state.set("success")
            self.emit("think", text="")
            return f"«{label}»: выполнено {ok}, не удалось {failed}."
        self.state.set("error")
        self.mood.on_error()
        self.emit("think", text="")
        return f"Не удалось выполнить «{label}»."

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
        ctx_text = self.context.snapshot_text()
        if ctx_text:
            system += "\n" + ctx_text
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
        self.state.set("processing")
        try:
            reply = self.ai.chat(messages, vision=image_bytes is not None)
        except Exception as exc:
            self._log(f"Ошибка ИИ: {exc}", level="error")
            self.state.set("error")
            self.mood.on_error()
            self.say("Не удалось связаться с нейросетью. Проверьте настройки ИИ.")
            return
        clean, ai_actions = AIClient.parse_reply(reply or "")
        if image_bytes is None:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": clean})
        if ai_actions and allow:
            self._run_workflow(ai_actions, label="задание ИИ")
            self.state.set("idle")
            self.say(clean)
            return
        self.state.set("idle")
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
            self.state.set("success")
            self.say(f"Отменила: {desc}")
        else:
            self.state.set("idle")
            self.say("Не нашла действий, которые можно отменить.")

    # ------------------------------------------------------------------
    # Подтверждения
    # ------------------------------------------------------------------
    def _set_pending(self, prompt, fn, speak=None):
        self._pending_confirm = (prompt, fn,
                                 datetime.datetime.now().timestamp() + 60)
        self.say((speak or prompt) + " Скажите «да» или «нет».")
        self.emit("ask", text=prompt)
        self.state.set("listening", "Жду подтверждения…")
        self.activity.add(f"Жду подтверждения: {prompt}", kind="confirm", icon="❓")

    def _handle_confirmation(self, norm) -> bool:
        if self._pending_choice:
            return self._handle_choice(norm)
        if not self._pending_confirm:
            return False
        prompt, fn, expires = self._pending_confirm
        if datetime.datetime.now().timestamp() > expires:
            self._pending_confirm = None
            self.say("Время подтверждения истекло, отмена.")
            return True
        if re.match(r"^(да|подтвержда\w*|давай|ага|ну да|yes|окей|ок|конечно)\W*$", norm):
            self._pending_confirm = None
            self.state.set("executing")
            self.say(self.personality_ack() or "Выполняю.")
            threading.Thread(target=self._safe_call, args=(fn,), daemon=True).start()
            return True
        if re.match(r"^(нет|не|отмена|отмен\w*|стоп|не надо|no)\W*$", norm):
            self._pending_confirm = None
            self.state.set("idle")
            self.say("Отмена.")
            return True
        return False

    # ---------- выбор из вариантов («похоже есть: krita / gimp») ----------
    NUM_WORDS = {"один": 1, "первый": 1, "первую": 1, "одну": 1,
                 "два": 2, "две": 2, "второй": 2, "вторую": 2,
                 "три": 3, "третий": 3, "третью": 3,
                 "четыре": 4, "четвёртый": 4, "четвертый": 4,
                 "пять": 5, "пятый": 5}

    def _set_choice(self, prompt, options):
        """Вопрос с вариантами [(label, fn), …]. «да» — первый, «2» — второй."""
        self._pending_choice = (options,
                                datetime.datetime.now().timestamp() + 60)
        names = ", ".join(f"{i}. {lbl}" for i, (lbl, _) in enumerate(options, 1))
        self.say(prompt + " " + names + ". Назовите номер или «нет».")
        self.emit("ask", text=prompt + "\n" + names)
        self.state.set("listening", "Жду выбора…")
        self.activity.add(f"Жду выбора: {prompt} [{names}]",
                          kind="confirm", icon="❓")

    def _handle_choice(self, norm) -> bool:
        options, expires = self._pending_choice
        if datetime.datetime.now().timestamp() > expires:
            self._pending_choice = None
            self.say("Время выбора истекло.")
            return True
        if re.match(r"^(нет|не|отмена|отмен\w*|стоп|не надо|no)\W*$", norm):
            self._pending_choice = None
            self.state.set("idle")
            self.say("Отмена.")
            return True
        pick = None
        if re.match(r"^(да|давай|ага|ну да|yes|окей|ок|конечно)\W*$", norm):
            pick = 1
        else:
            num = re.match(r"^\W*(\d+)", norm)
            if num and 1 <= int(num.group(1)) <= len(options):
                pick = int(num.group(1))
            else:
                for w, v in self.NUM_WORDS.items():
                    if re.search(rf"\b{w}\b", norm):
                        pick = v
                        break
        if pick is None or pick > len(options):
            return False    # не выбор — обрабатываем как обычную команду
        self._pending_choice = None
        label, fn = options[pick - 1]
        self._log(f"Выбрано: {label}")
        self.state.set("executing")
        self.say(self.personality_ack() or "Выполняю.")
        threading.Thread(target=self._safe_call, args=(fn,), daemon=True).start()
        return True

    # ---------- планы ----------
    def _offer_plan(self, plan, frustrated=False):
        if not plan.steps:
            self.state.set("idle")
            msg = ("В журнале не нашла вчерашних действий."
                   if plan.source == "history" else "Не смогла составить план.")
            self.say(msg)
            self._finish(msg, frustrated)
            return
        if len(plan.steps) == 1:
            step = plan.steps[0]
            if step.command:
                self._process(step.command, "plan", depth=1)
                return
            reply = self._execute_chain(step.actions, plan.title)
            self._finish(reply, frustrated)
            return
        self._log(plan.prompt().replace("\n", " · "))
        n = len(plan.steps)
        self._set_pending(f"{plan.prompt()}\nВыполнить?",
                          lambda: self._run_plan(plan),
                          speak=f"План «{plan.title}»: шагов {n}. Выполнить?")

    def _run_plan(self, plan):
        self.state.set("executing")
        total = len(plan.steps)
        done = failed_steps = 0
        self.activity.add(f"План «{plan.title}»: {total} шагов",
                          kind="workflow", icon="🗂")
        flat = [a for s in plan.steps if s.actions for a in s.actions]
        if flat:
            self.context.note("plan", plan.title, actions=flat)
        for i, step in enumerate(plan.steps, 1):
            self.emit("think", text=f"ШАГ {i}/{total} · {step.desc.upper()}")
            try:
                if step.command:
                    self._process(step.command, "plan", depth=1)
                    done += 1
                elif step.actions:
                    ok, bad = A.execute_actions(
                        step.actions,
                        A.ActionContext(say=self.say, log=self._log,
                                        config=self.config,
                                        permissions=self.permissions,
                                        activity=self.activity))
                    if ok and not bad:
                        done += 1
                    else:
                        failed_steps += 1
                else:
                    failed_steps += 1
            except Exception:
                failed_steps += 1
        self.emit("think", text="")
        if failed_steps == 0:
            self.state.set("verifying")
            self.emit("think", text="ПРОВЕРЯЮ РЕЗУЛЬТАТ")
            self.mood.on_success(count=done)
            self.state.set("success")
            msg = f"Готово: {plan.title}, все {total} шагов."
        else:
            self.state.set("error")
            self.mood.on_error()
            msg = f"«{plan.title}»: выполнено шагов {done} из {total}."
        self._finish(msg)

    # ---------- проактивность ----------
    def _on_proactive(self, code, text):
        self.activity.add(text, kind="proactive", icon="⚠")
        self._log(f"Проактивно: {text}", level="system")
        self.state.set("alert")
        if self.config.get("proactive_voice", True):
            self.say(text)
        t = threading.Timer(6.0, self._alert_back)
        t.daemon = True
        t.start()

    def _alert_back(self):
        if self.state.state == "alert":
            self.state.set("idle")

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
        self.state.set("idle")
        self.say(prefix + reply)

    def shutdown(self):
        self.context.stop()
