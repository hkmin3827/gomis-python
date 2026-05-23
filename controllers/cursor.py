import json
from pathlib import Path
import pyautogui
from core.hand_tracker import INDEX_TIP

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# 웹캠 데드존 마진 (cursor)
_MARGIN_LEFT   = 0.20
_MARGIN_RIGHT  = 0.20
_MARGIN_TOP    = 0.30
_MARGIN_BOTTOM = 0.30


class CursorController:
    def __init__(self):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._smoothing = cfg["cursor_smoothing"]
        self._screen_w, self._screen_h = pyautogui.size()
        self._prev_x: float | None = None
        self._prev_y: float | None = None

    def move(self, landmarks):
        """
        INDEX_TIP 위치 → 스크린 좌표 매핑.
        방향별 비대칭 마진으로 아래쪽 도달 문제 해결.
        """
        raw_x  = landmarks[INDEX_TIP].x
        raw_y  = landmarks[INDEX_TIP].y
        active_x = 1.0 - _MARGIN_LEFT - _MARGIN_RIGHT
        active_y = 1.0 - _MARGIN_TOP  - _MARGIN_BOTTOM
        nx = max(0.0, min(1.0, (raw_x - _MARGIN_LEFT) / active_x))
        ny = max(0.0, min(1.0, (raw_y - _MARGIN_TOP) / active_y))

        tx = nx * self._screen_w
        ty = ny * self._screen_h

        if self._prev_x is None:
            self._prev_x, self._prev_y = tx, ty

        sx = self._prev_x * self._smoothing + tx * (1 - self._smoothing)
        sy = self._prev_y * self._smoothing + ty * (1 - self._smoothing)
        self._prev_x, self._prev_y = sx, sy

        pyautogui.moveTo(
            max(0, min(self._screen_w - 1, int(sx))),
            max(0, min(self._screen_h - 1, int(sy))),
        )

    def click(self):
        pyautogui.click()

    def double_click(self):
        pyautogui.doubleClick()

    def reset(self):
        self._prev_x = None
        self._prev_y = None
