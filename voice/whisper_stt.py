"""
Whisper 기반 음성 인식 + 타이핑 모듈.
sounddevice로 실시간 녹음 → Whisper 로컬 추론 → 클립보드 붙여넣기 + Enter.
"""
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np

if getattr(sys, 'frozen', False):
    # 빌드된 exe — _internal/logs/ 에 기록
    LOG_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "logs"
else:
    # 개발 환경 — 프로젝트 루트/tasks/
    LOG_DIR = Path(__file__).parent.parent / "tasks"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "voice.log"

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

# faster-whisper / HuggingFace 내부 HTTP DEBUG 로그 억제
for _noisy in ("httpcore", "httpx", "huggingface_hub", "hf_hub_download", "filelock"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)


class VoiceTyper:
    """녹음 시작/종료 후 Whisper로 텍스트 변환 → 현재 포커스 창에 타이핑."""

    SAMPLE_RATE    = 16_000
    MAX_RECORD_SEC = 300  # 최대 녹음 시간 — 초과분은 자동 무시 (5분)

    def __init__(self, model_name: str = "small", language: str = "ko"):
        self._model_name = model_name
        self._language = language
        self._model = None
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self._model_ready = threading.Event()
        self._auto_stop_timer: threading.Timer | None = None
        self._target_hwnd: int = 0  # 녹음 시작 시점의 포커스 창 — 타이핑 대상

        # 앱 시작 시 백그라운드에서 미리 로드 → start() 호출 시 대기 없이 즉시 스트림 시작 가능
        threading.Thread(target=self._preload_model, daemon=True).start()
        log.info(f"VoiceTyper 초기화 완료 (model={model_name}, language={language}) — 백그라운드 모델 로드 시작")

    # ── 공개 API ──
    def start(self, max_sec: int = MAX_RECORD_SEC, auto_enter: bool = True,
              on_auto_stop=None,
              on_started=None) -> None:
        """녹음 시작. max_sec 초 후 자동 종료. on_started는 스트림 열린 직후, on_auto_stop은 자동 종료 시 호출."""
        log.info("녹음 시작 요청")
        # 녹음 시작 시점의 포커스 창 저장 — Whisper 완료 후 해당 창에 텍스트 입력
        try:
            import win32gui
            self._target_hwnd = win32gui.GetForegroundWindow()
            log.debug(f"타이핑 대상 창 저장: hwnd={self._target_hwnd}")
        except Exception:
            self._target_hwnd = 0
        if not self._model_ready.is_set():
            log.info("모델 로딩 대기 중…")
        self._model_ready.wait()
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
            blocksize=4096,   # 버퍼 크게 → TTS 직후 input overflow 방지
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info("녹음 스트림 시작됨")
        if on_started:
            on_started()

        # 자동 종료 타이머
        def _timeout():
            log.info(f"자동 종료 타이머 발동 ({max_sec}초)")
            self.stop_and_transcribe(auto_enter=auto_enter)
            if on_auto_stop:
                on_auto_stop()

        self._auto_stop_timer = threading.Timer(max_sec, _timeout)
        self._auto_stop_timer.daemon = True
        self._auto_stop_timer.start()
        log.info(f"자동 종료 타이머 설정: {max_sec}초")

    def stop_and_transcribe(self, auto_enter: bool = True, do_type: bool = True) -> str:
        """녹음 종료 → Whisper 추론. do_type=True면 클립보드 붙여넣기+Enter, False면 텍스트만 반환."""
        log.info("녹음 종료 요청")
        with self._lock:
            if not self._recording:
                return ""  # 이미 종료됨 (타이머/수동 중복 호출 방지)
            self._recording = False

        # 타이머가 살아있으면 취소
        if self._auto_stop_timer is not None:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None

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

        if not text:
            log.warning("인식 결과 없음 (빈 문자열)")
        elif do_type:
            self._type_text(text, auto_enter=auto_enter, target_hwnd=self._target_hwnd)
            log.info(f"타이핑 완료 (auto_enter={auto_enter})")

        return text

    def close(self) -> None:
        # 백그라운드 모델 로드 스레드가 끝날 때까지 대기 (Qt 종료 전 스레드 정리)
        self._model_ready.wait(timeout=10)
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("VoiceTyper 종료")

    # ── 내부 구현 ──
    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning(f"오디오 콜백 status: {status}")
        with self._lock:
            if self._recording:
                total = sum(len(c) for c in self._chunks)
                if total < self.SAMPLE_RATE * self.MAX_RECORD_SEC:
                    self._chunks.append(indata.copy())

    def _preload_model(self):
        try:
            self._load_model()
        except Exception as e:
            log.error(f"백그라운드 모델 로드 실패: {e}", exc_info=True)
        finally:
            self._model_ready.set()

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            if getattr(sys, 'frozen', False):
                # exe 번들 내장 모델 사용 — 인터넷/캐시 불필요
                model_path = str(Path(getattr(sys, "_MEIPASS", "")) / "whisper_model")
                log.info(f"Whisper 모델 로드 시작 (번들 내장): {model_path}")
                self._model = WhisperModel(model_path, device="cpu", compute_type="int8")
            else:
                log.info(f"Whisper 모델 로드 시작: {self._model_name} / device=cpu (faster-whisper)")
                self._model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
            log.info("Whisper 모델 로드 완료")

    def _transcribe(self, audio: np.ndarray) -> str:
        import noisereduce as nr
        # 녹음 초반 0.3초를 배경 소음 샘플로 추정해 제거
        noise_sample = audio[:int(self.SAMPLE_RATE * 0.3)]
        audio = nr.reduce_noise(y=audio, sr=self.SAMPLE_RATE,
                                y_noise=noise_sample, stationary=True)
        segments, _ = self._model.transcribe(
            audio,
            language=self._language,
            condition_on_previous_text=False,
            temperature=0,
            no_speech_threshold=0.6,
            beam_size=5,
            vad_filter=True,   # 무음 구간 자동 제거 → 추론 속도 향상
        )
        return "".join(seg.text for seg in segments).strip()

    @staticmethod
    def _type_text(text: str, auto_enter: bool, target_hwnd: int = 0) -> None:
        """클립보드 경유 붙여넣기 (한글 지원). auto_enter=True면 Enter 추가."""
        import pyperclip
        import pyautogui
        import time

        # 녹음 시작 시점의 창으로 포커스 복원 — Gomis 창이 아닌 사용자 입력창에 붙여넣기
        if target_hwnd:
            try:
                import win32gui
                win32gui.SetForegroundWindow(target_hwnd)
                time.sleep(0.15)  # 포커스 전환 대기
            except Exception:
                pass

        pyperclip.copy(text)
        time.sleep(0.05)  # 클립보드 반영 대기
        pyautogui.hotkey("ctrl", "v")
        if auto_enter:
            pyautogui.press("enter")
