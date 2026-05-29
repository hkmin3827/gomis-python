import pyautogui
from core.hand_tracker import INDEX_TIP

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ── 커서 감도 매핑 ────────────────────────────────────────────────
# speed 1-100 선형 매핑
#
# 마진: LR·TB 모두 25~35% 구간
#   - 25% 미만이면 MediaPipe 감지 불안정 구간에 걸려 화면 모서리 도달 불가
#   - 마진이 클수록 active zone이 좁아져 손을 조금만 움직여도 화면 전체 커버 → 빠름
#
# speed  1 → smoothing=0.95, LR=0.25, TB=0.25  (느리고 정밀)
# speed 50 → smoothing=0.75, LR=0.30, TB=0.30  (중간)
# speed100 → smoothing=0.55, LR=0.35, TB=0.35  (빠름)

def _speed_params(speed: int):
    s = max(1, min(100, int(speed)))
    t = (s - 1) / 99.0             # 0.0(s=1) → 1.0(s=100)
    smoothing = 0.95 - t * 0.40    # 0.95 → 0.55
    margin    = 0.25 + t * 0.10    # 0.25 → 0.35  (LR·TB 동일)
    return smoothing, margin, margin


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
