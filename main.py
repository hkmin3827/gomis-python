"""
Javis Motion Control — 엔트리포인트
"""

import sys
import json
import signal
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent / "config" / "settings.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 창 닫아도 트레이에 유지
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config   = load_config()
    features = config["features"]

    # ── 코어 초기화 ──────────────────────────────────────────────
    from core import Camera, HandTracker
    from core.gesture_engine import (
        GestureEngine,
        GESTURE_CURSOR, GESTURE_CLICK, GESTURE_DOUBLE_CLICK,
        GESTURE_DRAG_UP, GESTURE_DRAG_DOWN,
        GESTURE_ZOOM_IN, GESTURE_ZOOM_OUT,
        GESTURE_VOLUME_UP, GESTURE_VOLUME_DOWN,
        GESTURE_WINDOW_LEFT, GESTURE_WINDOW_RIGHT,
        GESTURE_WINDOW_ALT_START_RIGHT, GESTURE_WINDOW_ALT_START_LEFT,
        GESTURE_WINDOW_ALT_TAB, GESTURE_WINDOW_ALT_END,
        GESTURE_VOICE_START, GESTURE_VOICE_END,
    )
    from controllers import (
        CursorController, ScrollController,
        VolumeController, WindowSwitcher, ZoomController,
    )

    from voice.whisper_stt import VoiceTyper

    cam     = Camera()
    tracker = HandTracker()
    engine  = GestureEngine(tracker)

    cursor      = CursorController()
    scroll      = ScrollController()
    volume      = VolumeController()
    windows     = WindowSwitcher()
    zoom        = ZoomController()
    voice_typer = VoiceTyper(model_name="small")

    voice_state = {"status": "idle"}   # "idle" | "recording" | "transcribing"

    cam.open()

    # ── 제스처 처리 (PreviewWindow 의 타이머가 호출) ─────────────
    def run_frame():
        ok, frame = cam.read()
        if not ok:
            return None

        h, w  = frame.shape[:2]
        hands = tracker.process_all(frame)          # 양손 모두 감지
        hand  = hands[0] if hands else None
        gesture = engine.detect(hand, w, h)

        if hand:
            tracker.draw(frame, hand.landmarks)

        # ── 박수 감지 (음성 타이핑) ─────────────────────────────
        clap = engine.detect_clap(hands)
        if clap == GESTURE_VOICE_START and voice_state["status"] == "idle":
            voice_state["status"] = "recording"
            voice_typer.start()
            tray.notify("Javis 🎤", "녹음 중… 다시 박수치면 종료")

        elif clap == GESTURE_VOICE_END and voice_state["status"] == "recording":
            voice_state["status"] = "transcribing"
            tray.notify("Javis", "음성 인식 중…")

            def _do_transcribe():
                try:
                    text = voice_typer.stop_and_transcribe(auto_enter=True)
                    if text:
                        tray.notify("Javis ✅", f"입력: {text[:40]}")
                    else:
                        tray.notify("Javis", "인식된 텍스트 없음")
                except Exception as e:
                    tray.notify("Javis ❌", f"음성 인식 오류: {e}")
                finally:
                    voice_state["status"] = "idle"

            threading.Thread(target=_do_transcribe, daemon=True).start()

        # ── 단일 손 제스처 처리 ────────────────────────────────
        if features.get("cursor") and gesture == GESTURE_CURSOR and hand:
            cursor.move(hand.landmarks)

        if features.get("click"):
            if gesture == GESTURE_CLICK:
                cursor.click()
            elif gesture == GESTURE_DOUBLE_CLICK:
                cursor.double_click()

        if features.get("scroll"):
            scroll.handle(gesture)

        if features.get("volume"):
            volume.handle(gesture)

        if features.get("window_switch"):
            windows.handle(gesture)

        zoom.handle(gesture)

        handedness = hand.handedness if hand else None
        # 음성 녹음 중일 때 gesture 이름에 표시
        disp_gesture = f"🎤 {voice_state['status']}" if voice_state["status"] != "idle" else gesture
        return frame, disp_gesture, engine.state, handedness

    # ── UI 초기화 ────────────────────────────────────────────────
    from ui import PreviewWindow, TrayIcon

    preview = PreviewWindow(run_frame)
    tray    = TrayIcon()

    tray.quit_requested.connect(lambda: _shutdown(app, cam, tracker, windows, voice_typer))
    tray.debug_toggled.connect(preview.set_debug)
    tray.preview_toggled.connect(lambda: preview.show() if preview.isHidden() else preview.hide())

    tray.show()
    preview.show()
    tray.notify("Javis 시작", "손 제스처로 컴퓨터를 제어합니다.")

    sys.exit(app.exec_())


def _shutdown(app, cam, tracker, windows=None, voice_typer=None):
    if windows:
        windows.force_release()
    if voice_typer:
        voice_typer.close()
    cam.close()
    tracker.close()
    app.quit()


if __name__ == "__main__":
    main()
