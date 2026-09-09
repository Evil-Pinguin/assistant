# -*- coding: utf-8 -*-
"""Зрение AURA: скриншот → Vision AI (OpenAI-совместимый API)."""
import base64
import io


def grab_jpeg(max_side: int = 1280, quality: int = 80):
    """Скриншот всего экрана в JPEG-байтах. None, если не получилось."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=quality)
        return buf.getvalue()
    except Exception:
        return None


def to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def vision_messages(question: str, jpeg_bytes: bytes, system: str = "") -> list:
    """Сообщения для chat/completions с картинкой."""
    content = [
        {"type": "text", "text": question},
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{to_b64(jpeg_bytes)}"}},
    ]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    return messages
