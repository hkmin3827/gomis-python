"""
무료 TTS 모듈 — edge-tts(인터넷) 우선, 실패 시 pyttsx3(오프라인) 폴백.
"""
import asyncio
import logging
import os
import tempfile
import threading
import time

log = logging.getLogger("voice")

_VOICE = "ko-KR-HyunsuMultilingualNeural"   # edge-tts 한국어 고품질 음성


def speak(text: str) -> None:
    """TTS 재생 (블로킹). 백그라운드 스레드에서 호출 권장."""
    if not text:
        return
    log.info(f"TTS 시작: {text[:60]}")
    try:
        _speak_edge_tts(text)
        log.info("TTS 완료 (edge-tts)")
    except Exception as e:
        log.warning(f"edge-tts 실패 ({e}), pyttsx3 폴백")
        try:
            _speak_pyttsx3(text)
            log.info("TTS 완료 (pyttsx3)")
        except Exception as e2:
            log.error(f"TTS 모두 실패: {e2}", exc_info=True)


def speak_async(text: str, on_done=None) -> threading.Thread:
    """백그라운드 스레드에서 TTS 재생. on_done 콜백은 재생 완료 후 호출됨."""
    def _run():
        speak(text)
        if on_done:
            try:
                on_done()
            except Exception as e:
                log.error(f"speak_async on_done 오류: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── 내부 구현 ────────────────────────────────────────────────────────

def _speak_edge_tts(text: str) -> None:
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, _VOICE)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        try:
            await communicate.save(tmp_path)
            _play_mp3(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    asyncio.run(_run())


_mixer_ready = False


def _ensure_mixer() -> None:
    global _mixer_ready
    if not _mixer_ready:
        import pygame
        pygame.mixer.init()
        _mixer_ready = True


def _play_mp3(path: str) -> None:
    """pygame으로 mp3 재생 (블로킹). mixer는 앱 수명 동안 1회만 초기화."""
    import pygame
    _ensure_mixer()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.stop()


def _speak_pyttsx3(text: str) -> None:
    import pyttsx3
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
