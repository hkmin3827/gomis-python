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

# torch DLL을 Qt보다 먼저 초기화해야 WinError 1114 방지됨
# Qt가 DLL 검색 경로를 변경하기 전에 c10.dll 등을 로드
try:
    import torch  # noqa: F401  # type: ignore[import]
except Exception:
    pass

CONFIG_PATH = Path(__file__).parent / "config" / "settings.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    import PyQt5.QtWebEngineWidgets  # noqa: F401 — QApplication 전에 임포트 필수
    QApplication.setAttribute(Qt.ApplicationAttribute(4))  # 4 = AA_ShareOpenGLContexts
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 창 닫아도 트레이에 유지
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config   = load_config()
    features = config["features"]

    from core import Camera, HandTracker
    from core.gesture_engine import (
        GestureEngine,
        GESTURE_CURSOR, GESTURE_CLICK, GESTURE_DOUBLE_CLICK,
        GESTURE_VOICE_START, GESTURE_VOICE_END,
        GESTURE_CLAUDE_START, GESTURE_CLAUDE_END,
        GESTURE_LOCK_TOGGLE,
    )
    from controllers import (
        CursorController, ScrollController,
        VolumeController, WindowSwitcher, ZoomController,
    )

    from voice.whisper_stt import VoiceTyper
    from voice.claude_client import ask_claude
    from voice.tts import speak_async

    cam     = Camera()
    tracker = HandTracker()
    engine  = GestureEngine(tracker)

    cursor      = CursorController()
    scroll      = ScrollController()
    volume      = VolumeController()
    windows     = WindowSwitcher()
    zoom        = ZoomController()
    voice_typer = VoiceTyper(model_name="small")

    voice_state  = {"status": "idle"}   # "idle" | "recording" | "transcribing"
    claude_state = {"status": "idle"}   # "idle" | "recording" | "thinking"
    lock_state   = {"locked": False}

    cam.open()

    # PreviewWindow 의 타이머가 호출
    def run_frame():
        ok, frame = cam.read()
        if not ok:
            return None

        hands      = tracker.process_all(frame)
        both_hands = len(hands) >= 2
        hand       = hands[0] if hands else None

        gesture = engine.detect(None if both_hands else hand)

        for h in hands:
            tracker.draw(frame, h.landmarks)

        # ── 잠금 토글 감지 (잠금 중에도 항상 체크) ───────────────────
        lock_trigger = engine.detect_lock(hands)
        if lock_trigger == GESTURE_LOCK_TOGGLE:
            lock_state["locked"] = not lock_state["locked"]
            if lock_state["locked"]:
                dashboard.set_state("locked")
                tray.notify("Javis 🔒", "잠금 모드 ON — 양손 엄지 Up 1.5초로 해제")
            else:
                dashboard.set_state("idle")
                tray.notify("Javis 🔓", "잠금 모드 OFF")

        # ── 잠금 상태이면 이하 모든 제스처 처리 건너뜀 ──────────────
        if lock_state["locked"]:
            return frame, "[🔒 잠금 모드]", engine.state, hand.handedness if hand else None

        # ── 박수: 음성 타이핑 ──────────────────────────────────────────
        clap = engine.detect_clap(hands)
        if clap == GESTURE_VOICE_START and voice_state["status"] == "idle" \
                and claude_state["status"] == "idle":
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

        # ── 손가락 모으기: Claude 대화 ────────────────────────────────
        claude_trigger = engine.detect_claude_trigger(hands)
        if claude_trigger == GESTURE_CLAUDE_START and claude_state["status"] == "idle" \
                and voice_state["status"] == "idle":
            # 인사말 TTS → 완료 후 녹음 시작 (Claude 호출 없음)
            claude_state["status"] = "greeting"
            dashboard.set_state("speaking")
            tray.notify("Javis 🤖", "Gomis 인사 중…")

            def _start_recording():
                claude_state["status"] = "recording"
                dashboard.set_state("listening")
                voice_typer.start()
                tray.notify("Javis 🎤", "녹음 중… 다시 손 모으면 전송")

            speak_async("네 무엇을 도와드릴까요?", on_done=_start_recording)

        elif claude_trigger == GESTURE_CLAUDE_END and claude_state["status"] == "recording":
            claude_state["status"] = "thinking"
            dashboard.set_state("thinking")
            tray.notify("Javis", "Claude 생각 중…")

            def _do_claude():
                try:
                    text = voice_typer.stop_and_transcribe(auto_enter=False)
                    if not text:
                        tray.notify("Javis", "인식된 텍스트 없음")
                        claude_state["status"] = "idle"
                        dashboard.set_state("idle")
                        return
                    tray.notify("Javis 🤖", f"질문: {text[:40]}")
                    response = ask_claude(text)
                    if response:
                        tray.notify("Javis 💬", f"{response[:60]}")
                        dashboard.set_state("speaking")

                        def _after_response():
                            claude_state["status"] = "idle"
                            dashboard.set_state("idle")

                        speak_async(response, on_done=_after_response)
                    else:
                        tray.notify("Javis", "Claude 응답 없음")
                        claude_state["status"] = "idle"
                        dashboard.set_state("idle")
                except Exception as e:
                    tray.notify("Javis ❌", f"Claude 오류: {e}")
                    claude_state["status"] = "idle"
                    dashboard.set_state("idle")

            threading.Thread(target=_do_claude, daemon=True).start()

        # ── 단일 손 제스처 — 양손이면 발화 차단 ─────────────────────
        if not both_hands:
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
        if claude_state["status"] != "idle":
            disp_gesture = f"[{len(hands)}H] 🤖 {claude_state['status']}"
        elif voice_state["status"] != "idle":
            disp_gesture = f"[{len(hands)}H] 🎤 {voice_state['status']}"
        else:
            disp_gesture = f"[{len(hands)}H] {gesture}"
        return frame, disp_gesture, engine.state, handedness

    from ui import PreviewWindow, TrayIcon, GomisDashboard

    preview   = PreviewWindow(run_frame)
    tray      = TrayIcon()
    dashboard = GomisDashboard()

    tray.quit_requested.connect(lambda: _shutdown(app, cam, tracker, windows, voice_typer))
    tray.debug_toggled.connect(preview.set_debug)
    tray.preview_toggled.connect(lambda: preview.show() if preview.isHidden() else preview.hide())

    tray.show()
    preview.show()
    dashboard.show()
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
