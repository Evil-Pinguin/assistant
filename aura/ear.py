# -*- coding: utf-8 -*-
"""Слух AURA: микрофон + распознавание речи.

Два движка:
  * google — SpeechRecognition + бесплатный Google Web Speech API (нужен интернет);
  * vosk  — офлайн-распознавание (pip install vosk + модель).

Режимы:
  * с кодовым словом: сначала «аврора», затем команда;
  * прямой: каждая фраза — команда.
"""
import json
import re
import threading
import time

try:
    import speech_recognition as sr
    SR_OK = True
except Exception:  # pragma: no cover
    SR_OK = False


class Ear:
    def __init__(self, config, emit, on_text):
        self.config = config
        self.emit = emit                      # события для GUI
        self.on_text = on_text                # колбэк: распознанный текст -> Brain
        self.running = threading.Event()
        self.paused = threading.Event()       # «спим» до кодового слова
        self._push = threading.Event()        # кнопка «Слушать» (push-to-talk)
        self._thread = None
        self._vosk_model = None

    # ---------- публичный API ----------
    def start(self):
        if not SR_OK:
            self.emit("log", level="error",
                      msg="Микрофон недоступен: не установлен SpeechRecognition "
                          "(pip install SpeechRecognition PyAudio)")
            return False
        if self.is_alive:
            return True
        self.running.set()
        self._thread = threading.Thread(target=self._loop, name="ear", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.running.clear()
        self._push.set()  # разбудить поток, чтобы он увидел stop

    @property
    def is_alive(self):
        return bool(self._thread and self._thread.is_alive() and self.running.is_set())

    def listen_once(self):
        """Разовое прослушивание по кнопке (работает даже в режиме сна)."""
        if not self.is_alive:
            if not self.start():
                return False
        self._push.set()
        return True

    # ---------- вспомогательное ----------
    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower().replace("ё", "е")
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()

    def _match_wake(self, text: str) -> bool:
        wake = self.normalize(self.config.get("wake_word", "аврора"))
        if not wake:
            return True
        # «аврора», «авроры», «аврора слушай» и т.п.
        return any(tok.startswith(wake) for tok in text.split())

    # --- распознавание ---
    def _recognize(self, recognizer, source_audio) -> str:
        engine = (self.config.get("stt_engine") or "google").lower()
        if engine == "vosk":
            return self._recognize_vosk(source_audio)
        lang = self.config.get("language", "ru-RU")
        return recognizer.recognize_google(source_audio, language=lang)

    def _recognize_vosk(self, audio) -> str:
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError:
            raise RuntimeError("Vosk не установлен: pip install vosk")
        if self._vosk_model is None:
            path = self.config.get("vosk_model_path", "")
            if not path:
                raise RuntimeError("Не указан путь к модели Vosk (Настройки → Слух)")
            self.emit("log", level="system", msg=f"Загружаю модель Vosk: {path} …")
            self._vosk_model = Model(path)
        rec = KaldiRecognizer(self._vosk_model, 16000)
        rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
        return json.loads(rec.FinalResult()).get("text", "")

    # --- основной цикл ---
    def _loop(self):
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.energy_threshold = 300
        try:
            mic = sr.Microphone()
        except Exception as exc:
            self._mic_failed(exc)
            return
        try:
            with mic as source:
                self.emit("log", level="system", msg="Калибрую микрофон под шум…")
                r.adjust_for_ambient_noise(source, duration=1)
                self.emit("mic_state", active=True)
                self.emit("log", level="system", msg="Микрофон активен.")
                self._listen_loop(r, source)
        except Exception as exc:
            if self.running.is_set():
                self._mic_failed(exc)
        self.running.clear()
        self.emit("mic_state", active=False)

    def _mic_failed(self, exc):
        self.running.clear()
        self.emit("log", level="error",
                  msg=f"Микрофон недоступен: {exc}. Проверьте устройство и установку "
                      f"PyAudio (pip install PyAudio). Печатайте команды в окне управления.")
        self.emit("mic_state", active=False)

    def _listen_loop(self, r, source):
        while self.running.is_set():
            if self.paused.is_set() and not self._push.is_set():
                time.sleep(0.15)
                continue
            push_talk = self._push.is_set()
            self._push.clear()
            wake_required = self.config.get("require_wake_word", True)
            wait_label = ("Слушаю…" if (push_talk or not wake_required)
                          else "Жду кодовое слово…")
            self.emit("state", name="listening", label=wait_label)
            try:
                audio = r.listen(source, timeout=4 if not push_talk else 6,
                                 phrase_time_limit=6)
            except Exception:  # WaitTimeoutError и пр. — тишина, обычный цикл
                self.emit("state",
                          name="idle" if self.paused.is_set() else "listening",
                          label="Ожидаю…" if self.paused.is_set() else wait_label)
                continue

            try:
                text = self._recognize(r, audio)
            except RuntimeError as exc:
                self.emit("log", level="error", msg=str(exc))
                self.emit("state", name="alert", label="Ошибка распознавания")
                time.sleep(2)
                continue
            except Exception as exc:
                name = type(exc).__name__
                if name == "RequestError":
                    self.emit("log", level="error",
                              msg="Сервис распознавания недоступен (нет интернета?). "
                                  "Для офлайна: pip install vosk и укажите модель в настройках.")
                    self.emit("state", name="alert", label="Нет связи с сервисом")
                    time.sleep(2)
                else:  # UnknownValueError — не разобрал речь
                    self.emit("state", name="idle",
                              label="Не расслышал" if push_talk else wait_label)
                continue

            text = (text or "").strip()
            if not text:
                continue
            norm = self.normalize(text)

            # режим кодового слова
            if wake_required and not push_talk:
                if not self._match_wake(norm):
                    continue
                wake = self.normalize(self.config.get("wake_word", "аврора"))
                rest = " ".join(t for t in norm.split() if not t.startswith(wake))
                self.emit("heard", text=text)
                if rest:                            # команда прозвучала сразу
                    self.on_text(rest, "voice")
                else:                                # ждём команду следом
                    self.emit("state", name="listening", label="Слушаю команду…")
                    try:
                        audio2 = r.listen(source, timeout=5, phrase_time_limit=8)
                        cmd = self._recognize(r, audio2).strip()
                    except Exception:
                        cmd = ""
                    if cmd:
                        self.emit("heard", text=cmd)
                        self.on_text(cmd, "voice")
                    else:
                        self.emit("log", level="system", msg="Команда не расслышана.")
                continue

            # прямой режим / push-to-talk
            self.emit("heard", text=text)
            self.on_text(text, "voice")
