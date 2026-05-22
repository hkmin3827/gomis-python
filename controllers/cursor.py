import json
from pathlib import Path
import pyautogui
from core.hand_tracker import INDEX_TIP

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# 웹캠 가장자리 제외 비율: 상하좌우 각 20% 는 데드존
_MARGIN = 0.20


class CursorController:
    def __init__(self):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._smoothing = cfg["cursor_smoothing"]   # 0~1, 높을수록 부드럽고 느림
        self._screen_w, self._screen_h = pyautogui.size()
        self._prev_x: float | None = None
        self._prev_y: float | None = None

    def move(self, landmarks):
        """
        INDEX_TIP 위치 → 스크린 좌표 매핑.
        웹캠 [MARGIN, 1-MARGIN] 범위만 활성 영역으로 사용해
        가장자리 손 인식 소실 문제를 완화.
        """
        active = 1.0 - 2 * _MARGIN
        raw_x  = landmarks[INDEX_TIP].x
        raw_y  = landmarks[INDEX_TIP].y
        # X 축 반전: 웹캠은 거울상이므로 손 움직임과 커서 방향을 일치시킴
        nx = max(0.0, min(1.0, 1.0 - (raw_x - _MARGIN) / active))
        ny = max(0.0, min(1.0, (raw_y - _MARGIN) / active))

        tx = nx * self._screen_w
        ty = ny * self._screen_h

        if self._prev_x is None:
            self._prev_x, self._prev_y = tx, ty

        # 지수 이동 평균으로 떨림 완화
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
