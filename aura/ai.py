# -*- coding: utf-8 -*-
"""ИИ-мозг AURA: любой OpenAI-совместимый API + Vision.

Подходят: OpenAI, OpenRouter, DeepSeek, Groq, Mistral,
локальные Ollama (http://localhost:11434/v1) и LM Studio (http://localhost:1234/v1).

Важно: ИИ — мозг, а не исполнитель. Он предлагает действия блоком ```aura …```,
а выполняет их безопасный Tool Router с системой разрешений.
"""
import json
import re

import requests

ACTION_BLOCK_RE = re.compile(r"```(?:aura|jarvis|action)\s*(.*?)```", re.S)

PERSONALITY_STYLES = {
    "professional": "Тон: профессиональный, сдержанный, как у ассистента крупной компании.",
    "friendly": "Тон: дружелюбный и тёплый, обращайтесь на «вы», слегка непринуждённо.",
    "jarvis": ("Тон: вежливый британский дворецкий в стиле Джарвиса из «Железного человека», "
               "с лёгкой иронией."),
    "anime": "Тон: энергичный персонаж аниме, лёгкий и позитивный, иногда «~» в конце фраз.",
}

SYSTEM_PROMPT = (
    "Ты — AURA (Аврора), голосовой ИИ-ассистент пользователя на его компьютере. "
    "Отвечай по-русски, кратко (1–3 предложения) и по делу. Ответ будет произнесён "
    "голосом, поэтому без markdown, списков и эмодзи."
)

ACTIONS_PROMPT = """
Если просьба требует действия на компьютере, добавь В КОНЦЕ ответа блок:
```aura
{"say": "Короткая фраза для озвучки", "actions": [{"type": "...", "target": "..."}]}
```
Доступные типы действий:
- open_url — открыть сайт: {"type": "open_url", "target": "https://youtube.com"}
- open_app — открыть приложение/файл: {"type": "open_app", "target": "notepad"}
- close_app — закрыть приложение: {"type": "close_app", "target": "chrome"}
- shell — команда системы: {"type": "shell", "target": "ipconfig"}
- press — горячие клавиши: {"type": "press", "target": "win+d"}
- type_text — напечатать текст: {"type": "type_text", "target": "Привет"}
- click — клик мышью по координатам: {"type": "click", "target": "960,540"}
- scroll — прокрутка: {"type": "scroll", "target": "-500"}
- volume — громкость: {"type": "volume", "target": "up|down|mute|0-100"}
- say — сказать фразу: {"type": "say", "text": "Готово"}
- wait — пауза, секунды: {"type": "wait", "target": "2"}
Действия выполняет система безопасности AURA: пользователь может запретить часть из них.
Используй действия, только когда пользователь явно попросил что-то сделать.
Блок должен быть последним в ответе и точно следовать формату выше."""


class AIClient:
    def __init__(self, config, emit=None):
        self.config = config
        self.emit = emit or (lambda *a, **k: None)

    @property
    def ready(self) -> bool:
        return bool(self.config.get("ai_enabled")) and bool(self.config.get("ai_base_url"))

    # ------------------------------------------------------------------
    def chat(self, messages, max_tokens=300, vision=False) -> str:
        base = (self.config.get("ai_base_url") or "").rstrip("/")
        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = self.config.get("ai_api_key", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": (self.config.get("vision_model") or self.config.get("ai_model", ""))
            if vision else self.config.get("ai_model", "gpt-4o-mini"),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

    def test_connection(self) -> str:
        return self.chat([{"role": "user", "content": "Ответь одним словом: связь есть?"}])

    # ------------------------------------------------------------------
    @staticmethod
    def parse_reply(reply: str):
        """Возвращает (текст_для_озвучки, actions|None)."""
        actions = None
        say = None
        m = ACTION_BLOCK_RE.search(reply or "")
        if m:
            try:
                parsed = json.loads(m.group(1))
                actions = parsed.get("actions") or None
                say = parsed.get("say")
            except json.JSONDecodeError:
                say = None
            reply = (reply[:m.start()] + " " + reply[m.end():]).strip()
        clean = re.sub(r"```.*?```", "", reply or "", flags=re.S).strip()
        clean = re.sub(r"\s+", " ", clean).strip()
        return say or clean, actions
