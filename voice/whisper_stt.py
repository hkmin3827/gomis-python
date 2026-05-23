"""
Whisper 기반 음성 인식 + 타이핑 모듈.
sounddevice로 실시간 녹음 → Whisper 로컬 추론 → 클립보드 붙여넣기 + Enter.
"""
import threading
import numpy as np


class VoiceTyper:
    """녹음 시작/종료 후 Whisper로 텍스트 변환 → 현재 포커스 창에 타이핑."""

    SAMPLE_RATE = 16_000

    def __init__(self, model_name: str = "small"):
        self._model_name = model_name
        self._model = None          # 첫 사용 시 lazy load
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    # ── 공개 API ──────────────────────────────────────────────────

    def start(self) -> None:
        """녹음 시작. 별도 스레드 없이 sounddevice InputStream 사용."""
        import sounddevice as sd
        with self._lock:
            self._chunks = []
            self._recording = True

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop_and_transcribe(self, auto_enter: bool = True) -> str:
        """녹음 종료 → Whisper 추론 → 클립보드 붙여넣기 + Enter.
        반환값: 인식된 텍스트 (UI 표시용).
        """
        with self._lock:
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            chunks = list(self._chunks)

        if not chunks:
            return ""

        audio = np.concatenate(chunks, axis=0).flatten()
        text = self._transcribe(audio)

        if text:
            self._type_text(text, auto_enter=auto_enter)

        return text

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    # ── 내부 구현 ─────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())

    def _load_model(self):
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self._model_name)

    def _transcribe(self, audio: np.ndarray) -> str:
        self._load_model()
        result = self._model.transcribe(audio, language="ko", fp16=False)
        return result["text"].strip()

    @staticmethod
    def _type_text(text: str, auto_enter: bool) -> None:
        """클립보드 경유 붙여넣기 (한글 지원). auto_enter=True면 Enter 추가."""
        import pyperclip
        import pyautogui
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        if auto_enter:
            pyautogui.press("enter")
