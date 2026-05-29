import pyautogui
from core.hand_tracker import INDEX_TIP

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ── 커서 감도 매핑 ────────────────────────────────────────────────
# speed=70 이 원래 기본값(smoothing=0.70, LR=0.20, TB=0.30)과 일치하는 앵커
# speed  1 → smoothing=0.95, LR=0.10, TB=0.15  (느리고 정밀)
# speed 70 → smoothing=0.70, LR=0.20, TB=0.30  (기본값 — 원래 하드코딩 값)
# speed100 → smoothing=0.55, LR=0.30, TB=0.35  (빠름)
#
# 마진이 커질수록 active zone이 작아져 → 같은 손 움직임으로 화면을 더 빠르게 커버

def _speed_params(speed: int):
    s = max(1, min(100, int(speed)))
    if s <= 70:
        t = (s - 1) / 69          # 0.0(s=1) → 1.0(s=70)
        smoothing  = 0.95 - t * (0.95 - 0.70)   # 0.95 → 0.70
        margin_lr  = 0.10 + t * (0.20 - 0.10)   # 0.10 → 0.20
        margin_tb  = 0.15 + t * (0.30 - 0.15)   # 0.15 → 0.30
    else:
        t = (s - 70) / 30          # 0.0(s=70) → 1.0(s=100)
        smoothing  = 0.70 - t * (0.70 - 0.55)   # 0.70 → 0.55
        margin_lr  = 0.20 + t * (0.30 - 0.20)   # 0.20 → 0.30
        margin_tb  = 0.30 + t * (0.35 - 0.30)   # 0.30 → 0.35
    return smoothing, margin_lr, margin_tb


class CursorController:
    def __init__(self):
        self._screen_w, self._screen_h = pyautogui.size()
        self._prev_x: float | None = None
        self._prev_y: float | None = None
        self._live: dict | None = None

    def set_settings(self, live: dict) -> None:
        self._live = live

    def move(self, landmarks):
        speed = self._live.get("cursor_speed", 70) if self._live else 70
        smoothing, margin_lr, margin_tb = _speed_params(speed)

        raw_x = landmarks[INDEX_TIP].x
        raw_y = landmarks[INDEX_TIP].y

        # 대칭 마진 적용
        active_x = max(0.01, 1.0 - margin_lr * 2)
        active_y = max(0.01, 1.0 - margin_tb * 2)
        nx = max(0.0, min(1.0, (raw_x - margin_lr) / active_x))
        ny = max(0.0, min(1.0, (raw_y - margin_tb) / active_y))

        tx = nx * self._screen_w
        ty = ny * self._screen_h

        if self._prev_x is None:
            self._prev_x, self._prev_y = tx, ty

        sx = self._prev_x * smoothing + tx * (1 - smoothing)
        sy = self._prev_y * smoothing + ty * (1 - smoothing)
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
