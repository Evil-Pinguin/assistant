# -*- coding: utf-8 -*-
"""Голос AURA: TTS через pyttsx3 в отдельном потоке с очередью.

pyttsx3 не потокобезопасен, поэтому весь движок живёт в одном рабочем потоке.
Если TTS недоступен (нет пакета/голоса) — ассистент продолжает работать,
ответы пишутся в журнал.
"""
import queue
import threading
import time


class Voice:
    def __init__(self, config, emit):
        """emit(kind, **data) — шина событий для GUI."""
        self.config = config
        self.emit = emit
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._stop = threading.Event()
        self._engine = None
        self._failed = False          # после критической ошибки TTS отключается
        self.speaking = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="voice", daemon=True)
        self.thread.start()

    # ---------- публичный API ----------
    def say(self, text: str):
        """Произнести текст (неблокирующе)."""
        text = (text or "").strip()
        if not text or self._failed:
            return
        self._q.put(text)

    def stop_speaking(self):
        """Прервать текущую фразу."""
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass

    def available_voices(self):
        """Список (id, name) установленных голосов — для настроек в GUI."""
        try:
            import pyttsx3
            eng = pyttsx3.init()
            voices = [(v.id, getattr(v, "name", v.id)) for v in eng.getProperty("voices")]
            try:
                eng.stop()
            except Exception:
                pass
            return voices
        except Exception as exc:
            self.emit("log", level="error", msg=f"Не удалось получить список голосов: {exc}")
            return []

    def shutdown(self):
        self._stop.set()
        self.stop_speaking()
        self._q.put(None)

    # ---------- внутреннее ----------
    def _apply_settings(self, engine):
        engine.setProperty("rate", int(self.config.get("tts_rate", 175)))
        engine.setProperty("volume", float(self.config.get("tts_volume", 1.0)))
        voice_id = self.config.get("tts_voice_id", "")
        if voice_id:
            try:
                engine.setProperty("voice", voice_id)
            except Exception:
                pass

    def _init_engine(self):
        import pyttsx3
        engine = pyttsx3.init()
        self._apply_settings(engine)
        return engine

    def _speak(self, text: str) -> bool:
        if self._engine is None:
            self._engine = self._init_engine()
        self._apply_settings(self._engine)
        self._engine.say(text)
        self._engine.runAndWait()
        return True

    def _loop(self):
        while not self._stop.is_set():
            try:
                text = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if text is None:
                break
            if not self.config.get("tts_enabled", True):
                continue
            try:
                self.speaking.set()
                self.emit("say_start", text=text)
                ok = False
                try:
                    ok = self._speak(text)
                except Exception:
                    # одна повторная попытка с пересозданием движка
                    time.sleep(0.3)
                    try:
                        self._engine = self._init_engine()
                        ok = self._speak(text)
                    except Exception as exc2:
                        self._failed = True
                        self.emit("log", level="error",
                                  msg=f"Голос отключён (TTS недоступен): {exc2}. "
                                      f"Ответы видны в журнале. На Linux установите: "
                                      f"sudo apt install espeak-ng")
                if ok:
                    # даём аудиобуферу доиграть
                    time.sleep(0.05)
            finally:
                self.speaking.clear()
                self.emit("say_end")
