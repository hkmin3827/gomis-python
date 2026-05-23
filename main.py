"""
Javis Motion Control — 엔트리포인트
"""

import sys
import json
import signal
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
    )
    from controllers import (
        CursorController, ScrollController,
        VolumeController, WindowSwitcher, ZoomController,
    )

    cam     = Camera()
    tracker = HandTracker()
    engine  = GestureEngine(tracker)

    cursor  = CursorController()
    scroll  = ScrollController()
    volume  = VolumeController()
    windows = WindowSwitcher()
    zoom    = ZoomController()

    cam.open()

    # ── 제스처 처리 (PreviewWindow 의 타이머가 호출) ─────────────
    def run_frame():
        ok, frame = cam.read()
        if not ok:
            return None

        h, w   = frame.shape[:2]
        hand   = tracker.process(frame)
        gesture = engine.detect(hand, w, h)

        if hand:
            tracker.draw(frame, hand.landmarks)

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
        return frame, gesture, engine.state, handedness

    # ── UI 초기화 ────────────────────────────────────────────────
    from ui import PreviewWindow, TrayIcon

    preview = PreviewWindow(run_frame)
    tray    = TrayIcon()

    tray.quit_requested.connect(lambda: _shutdown(app, cam, tracker))
    tray.debug_toggled.connect(preview.set_debug)
    tray.preview_toggled.connect(lambda: preview.show() if preview.isHidden() else preview.hide())

    tray.show()
    preview.show()
    tray.notify("Javis 시작", "손 제스처로 컴퓨터를 제어합니다.")

    sys.exit(app.exec_())


def _shutdown(app, cam, tracker):
    cam.close()
    tracker.close()
    app.quit()


if __name__ == "__main__":
    main()
