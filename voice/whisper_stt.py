"""
Whisper 기반 음성 인식 + 타이핑 모듈.
sounddevice로 실시간 녹음 → Whisper 로컬 추론 → 클립보드 붙여넣기 + Enter.
"""
import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np

LOG_PATH = Path(__file__).parent.parent / "tasks" / "voice.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_PATH, encoding="utf-8",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("voice")


class VoiceTyper:
    """녹음 시작/종료 후 Whisper로 텍스트 변환 → 현재 포커스 창에 타이핑."""

    SAMPLE_RATE = 16_000

    def __init__(self, model_name: str = "small"):
        self._model_name = model_name
        self._model = None
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self._model_ready = threading.Event()

        # 앱 시작 시 백그라운드에서 미리 로드 → start() 호출 시 대기 없이 즉시 스트림 시작 가능
        threading.Thread(target=self._preload_model, daemon=True).start()
        log.info(f"VoiceTyper 초기화 완료 (model={model_name}) — 백그라운드 모델 로드 시작")

    # ── 공개 API ──────────────────────────────────────────────────

    def start(self) -> None:
        """녹음 시작. 모델이 아직 로딩 중이면 완료될 때까지 대기 후 즉시 스트림 시작."""
        log.info("녹음 시작 요청")
        if not self._model_ready.is_set():
            log.info("모델 로딩 대기 중…")
        self._model_ready.wait()  # 이미 로드됐으면 즉시 통과
        if self._model is None:
            raise RuntimeError("Whisper 모델 로드 실패")

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
        log.info("녹음 스트림 시작됨")

    def stop_and_transcribe(self, auto_enter: bool = True) -> str:
        """녹음 종료 → Whisper 추론 → 클립보드 붙여넣기 + Enter."""
        log.info("녹음 종료 요청")
        with self._lock:
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("녹음 스트림 닫힘")

        with self._lock:
            chunks = list(self._chunks)

        if not chunks:
            log.warning("녹음된 오디오 없음 (chunks 비어있음)")
            return ""

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / self.SAMPLE_RATE
        log.info(f"오디오 수집 완료: {duration:.2f}초, {len(audio)} samples")

        t0 = time.time()
        try:
            text = self._transcribe(audio)
        except Exception as e:
            log.error(f"Whisper 추론 실패: {e}", exc_info=True)
            raise
        elapsed = time.time() - t0
        log.info(f"Whisper 추론 완료: {elapsed:.2f}초 → '{text}'")

        if text:
            self._type_text(text, auto_enter=auto_enter)
            log.info(f"타이핑 완료 (auto_enter={auto_enter})")
        else:
            log.warning("인식 결과 없음 (빈 문자열)")

        return text

    def close(self) -> None:
        # 백그라운드 모델 로드 스레드가 끝날 때까지 대기 (Qt 종료 전 스레드 정리)
        self._model_ready.wait(timeout=10)
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("VoiceTyper 종료")

    # ── 내부 구현 ─────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning(f"오디오 콜백 status: {status}")
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())

    def _preload_model(self):
        try:
            self._load_model()
        except Exception as e:
            log.error(f"백그라운드 모델 로드 실패: {e}", exc_info=True)
        finally:
            self._model_ready.set()  # 실패해도 set → start()가 무한 대기하지 않도록

    def _load_model(self):
        if self._model is None:
            log.info(f"Whisper 모델 로드 시작: {self._model_name} / device=cpu")
            import whisper
            self._model = whisper.load_model(self._model_name, device="cpu")
            log.info("Whisper 모델 로드 완료")

    def _transcribe(self, audio: np.ndarray) -> str:
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
