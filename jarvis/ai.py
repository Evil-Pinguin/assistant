# -*- coding: utf-8 -*-
"""Подключение ИИ: любой OpenAI-совместимый API.

Подходит: OpenAI, OpenRouter, DeepSeek, Groq, Mistral,
локальные Ollama (http://localhost:11434/v1) и LM Studio (http://localhost:1234/v1).
"""
import json
import re

import requests

ACTION_BLOCK_RE = re.compile(r"```(?:jarvis|action)\s*(\{.*?\})\s*```", re.S)

SYSTEM_PROMPT = (
    "Ты — Джарвис, голосовой ИИ-ассистент пользователя, как из фильма «Железный человек». "
    "Отвечай по-русски, кратко (1–3 предложения), дружелюбно и по делу. "
    "Ответ будет произнесён голосом, поэтому без markdown, списков и эмодзи."
)

ACTIONS_PROMPT = """
Если просьба пользователя требует действия на компьютере, добавь В КОНЦЕ ответа блок:
```jarvis
{"say": "Короткая фраза для озвучки", "actions": [{"type": "...", "target": "..."}]}
```
Доступные типы действий:
- open_url — открыть сайт: {"type": "open_url", "target": "https://youtube.com"}
- open_app — открыть приложение: {"type": "open_app", "target": "notepad"}
- shell — выполнить команду системы: {"type": "shell", "target": "ipconfig"}
- press — нажать горячие клавиши: {"type": "press", "target": "win+d"}
- type_text — напечатать текст: {"type": "type_text", "target": "Привет"}
- volume — громкость: {"type": "volume", "target": "up|down|mute"}
Используй действия только когда пользователь явно попросил что-то сделать. Блок обязателен
в формате кода выше и должен быть последним в ответе."""


class AIClient:
    def __init__(self, config, emit=None):
        self.config = config
        self.emit = emit or (lambda *a, **k: None)

    @property
    def ready(self) -> bool:
        return bool(self.config.get("ai_enabled")) and bool(self.config.get("ai_base_url"))

    def chat(self, messages, max_tokens: int = 300) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}]"""
        base = (self.config.get("ai_base_url") or "").rstrip("/")
        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = self.config.get("ai_api_key", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self.config.get("ai_model", "gpt-4o-mini"),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

    def test_connection(self) -> str:
        """Быстрая проверка из настроек."""
        reply = self.chat([{"role": "user", "content": "Ответь одним словом: связь есть?"}])
        return reply or "Пустой ответ"

    # --- разбор блока действий в ответе ИИ ---
    @staticmethod
    def parse_reply(reply: str):
        """Возвращает (текст_для_озвучки, actions|None)."""
        actions = None
        m = ACTION_BLOCK_RE.search(reply)
        if m:
            try:
                parsed = json.loads(m.group(1))
                actions = parsed.get("actions") or None
                say = parsed.get("say")
            except json.JSONDecodeError:
                say = None
            reply = (reply[:m.start()] + " " + reply[m.end():]).strip()
        clean = re.sub(r"```.*?```", "", reply, flags=re.S).strip()
        clean = re.sub(r"\s+", " ", clean).strip()
        return say or clean, actions
