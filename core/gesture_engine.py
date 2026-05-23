"""
제스처 판별 엔진 — 상태 기계(State Machine) 방식.

상태 전이:
  IDLE → CURSOR / DRAG / ZOOM / VOLUME  (3 프레임 연속 포즈 유지 후 확정)
  연속 상태 → IDLE  (손바닥 펴기로만 종료, 이후 0.5 s 쿨다운)
  클릭/더블클릭: 어떤 상태에서든 즉시 발화 (오픈팜 → 오므리기 순서 필수)
  창 전환: 오픈팜 + 수평 스와이프 (상태 무관, 방향만으로 판별)
  줌: 3-finger 핀치(엄지+검지+중지 끝 삼각형) 진입 → 벌리면 줌인 / 좁히면 줌아웃
"""

import json
import time
from enum import Enum
from pathlib import Path

from .hand_tracker import (
    HandTracker, HandResult,
    WRIST, THUMB_TIP, THUMB_IP,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP,  RING_PIP,  RING_MCP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

# ── 제스처 이름 상수 ─────────────────────────────────────────────
GESTURE_NONE          = "none"
GESTURE_CURSOR        = "cursor"
GESTURE_CLICK         = "click"
GESTURE_DOUBLE_CLICK  = "double_click"
GESTURE_DRAG_UP       = "drag_up"
GESTURE_DRAG_DOWN     = "drag_down"
GESTURE_ZOOM_IN       = "zoom_in"
GESTURE_ZOOM_OUT      = "zoom_out"
GESTURE_VOLUME_UP     = "volume_up"
GESTURE_VOLUME_DOWN   = "volume_down"
GESTURE_WINDOW_RIGHT  = "window_right"
GESTURE_WINDOW_LEFT   = "window_left"


# ── 상태 ─────────────────────────────────────────────────────────
class State(Enum):
    IDLE    = "idle"
    CURSOR  = "cursor"
    DRAG    = "drag"
    ZOOM    = "zoom"
    VOLUME  = "volume"


class GestureEngine:
    _CONFIRM_FRAMES = 3
    _IDLE_COOLDOWN  = 0.5

    # 줌 — 3-finger 핀치 임계값
    _ZOOM_ENTRY_RATIO  = 0.42   # 삼각형 지름 / 손 기준값 < 이 값이면 핀치 상태
    _ZOOM_DELTA        = 0.03   # 줌 발화 최소 변화량 (정규화 좌표)

    def __init__(self, tracker: HandTracker):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._click_threshold = cfg["click_threshold"]
        self._tracker = tracker

        self._state = State.IDLE

        # 드래그
        self._prev_drag_y: float | None = None
        self._drag_accum:  float        = 0.0
        self._DRAG_STEP                 = 5

        # 줌 — 방향 고정 (오픈팜 전까지 같은 방향만 발화)
        self._zoom_last_fired: float | None = None
        self._zoom_last_dir:   str | None   = None   # "in" | "out"

        # 볼륨
        self._last_volume_time = 0.0
        self._volume_cooldown  = 1.0 / 3.0

        # 클릭
        self._last_click_time  = 0.0
        self._double_click_gap = 0.4
        self._curl_active      = False
        self._palm_was_open    = False

        # 창 전환
        self._last_window_time  = 0.0
        self._window_cooldown   = 1.0
        self._window_once_fired = False
        self._pos_history: list[tuple[float, float]] = []
        self._swipe_win         = 0.5
        self._swipe_dist        = 0.30
        self._swipe_min_vel     = 0.20

        # 상태 진입 확정
        self._pending_desire: str | None = None
        self._pending_count: int = 0

        self._idle_cooldown_until: float = 0.0

    # ── 공개 메서드 ───────────────────────────────────────────────

    def detect(self, hand: HandResult | None, frame_w: int, frame_h: int) -> str:
        if hand is None:
            self._state = State.IDLE
            self._reset_tracking()
            self._curl_active = False
            return GESTURE_NONE

        lm   = hand.landmarks
        side = hand.handedness
        now  = time.time()

        # ── 손목 위치 이력 누적 (상태 무관) ──────────────────────
        self._pos_history = [(x, t) for x, t in self._pos_history if now - t < self._swipe_win]
        self._pos_history.append((lm[WRIST].x, now))

        if self._window_once_fired and now - self._last_window_time >= self._window_cooldown:
            self._window_once_fired = False
            self._pos_history.clear()

        # ── 창 전환: 오픈팜 + 수평 스와이프 (상태 무관) ──────────
        if _is_open_palm(lm):
            swipe = self._check_swipe()
            if swipe != GESTURE_NONE:
                return swipe

        # ── 클릭/더블클릭 (ZOOM 상태 제외) ──────────────────────
        is_open = _is_open_palm(lm)
        is_curl = _is_curl(lm)

        if is_open:
            self._palm_was_open = True
            self._curl_active   = False

        if is_curl and self._state != State.ZOOM:
            if self._palm_was_open and not self._curl_active:
                self._curl_active   = True
                self._palm_was_open = False
                now = time.time()
                gap = now - self._last_click_time
                if 0 < gap < self._double_click_gap:
                    self._last_click_time = 0.0
                    return GESTURE_DOUBLE_CLICK
                self._last_click_time = now
                return GESTURE_CLICK
            elif not self._palm_was_open:
                self._curl_active = True
            return GESTURE_NONE

        if not is_curl:
            self._curl_active = False

        # ── 손바닥 펴기 → 연속 제스처 종료 ───────────────────────
        if self._state != State.IDLE and _is_open_palm(lm):
            self._state = State.IDLE
            self._reset_tracking()
            self._idle_cooldown_until = time.time() + self._IDLE_COOLDOWN
            return GESTURE_NONE

        # ── 연속 상태 처리 ────────────────────────────────────────
        if self._state == State.CURSOR:
            return GESTURE_CURSOR if _is_cursor(lm) else GESTURE_NONE

        if self._state == State.DRAG:
            return self._handle_drag(lm, frame_h)

        if self._state == State.ZOOM:
            return self._handle_zoom(lm)

        if self._state == State.VOLUME:
            return self._handle_volume(side)

        return self._detect_from_idle(lm, side, frame_w, frame_h)

    @property
    def state(self) -> str:
        return self._state.value

    # ── 내부 메서드 ───────────────────────────────────────────────

    def _detect_from_idle(self, lm, side, frame_w, frame_h) -> str:
        now = time.time()

        if now < self._idle_cooldown_until:
            self._pending_desire = None
            self._pending_count  = 0
            return GESTURE_NONE

        # 포즈 감지 우선순위: zoom_gun > cursor > drag > volume
        desire: str | None = None
        if _is_gun_pose(lm, side):
            desire = "zoom_gun"
        elif _is_cursor(lm):
            desire = "cursor"
        elif _is_drag_pose(lm):
            desire = "drag"
        elif _is_shaka(lm):
            desire = "volume"

        if desire is None:
            self._pending_desire = None
            self._pending_count  = 0
            return GESTURE_NONE

        if desire == self._pending_desire:
            self._pending_count += 1
        else:
            self._pending_desire = desire
            self._pending_count  = 1

        # 드래그는 V자 유지가 어려우므로 1프레임 즉시 진입
        confirm_needed = 1 if desire == "drag" else self._CONFIRM_FRAMES
        if self._pending_count < confirm_needed:
            return GESTURE_NONE

        self._pending_desire = None
        self._pending_count  = 0

        if desire == "zoom_gun":
            self._state = State.ZOOM
            self._zoom_last_fired = _thumb_index_dist(lm)
            self._zoom_last_dir   = None
            return GESTURE_NONE

        if desire == "cursor":
            self._state = State.CURSOR
            return GESTURE_CURSOR

        if desire == "drag":
            self._state = State.DRAG
            self._prev_drag_y = lm[INDEX_TIP].y
            return GESTURE_NONE

        if desire == "volume":
            self._state = State.VOLUME
            return GESTURE_NONE

        return GESTURE_NONE

    def _check_swipe(self) -> str:
        if self._window_once_fired:
            return GESTURE_NONE
        if len(self._pos_history) < 5:
            return GESTURE_NONE
        now = time.time()
        if now - self._last_window_time < self._window_cooldown:
            return GESTURE_NONE

        xs = [x for x, _ in self._pos_history]
        ts = [t for _, t in self._pos_history]
        displacement = xs[-1] - xs[0]
        duration = max(ts[-1] - ts[0], 1e-6)
        velocity = displacement / duration

        if abs(velocity) > self._swipe_min_vel and abs(displacement) > self._swipe_dist:
            is_right_swipe = displacement > 0  # flip 적용 후 자연 방향
            self._last_window_time  = now
            self._window_once_fired = True
            self._pos_history.clear()
            return GESTURE_WINDOW_RIGHT if is_right_swipe else GESTURE_WINDOW_LEFT

        return GESTURE_NONE

    def _handle_drag(self, lm, frame_h) -> str:
        curr_y = lm[INDEX_TIP].y
        if self._prev_drag_y is None:
            self._prev_drag_y = curr_y
            return GESTURE_NONE

        delta = (curr_y - self._prev_drag_y) * frame_h
        self._prev_drag_y = curr_y
        self._drag_accum += delta

        if self._drag_accum < -self._DRAG_STEP:
            self._drag_accum += self._DRAG_STEP
            return GESTURE_DRAG_UP
        if self._drag_accum > self._DRAG_STEP:
            self._drag_accum -= self._DRAG_STEP
            return GESTURE_DRAG_DOWN
        return GESTURE_NONE

    def _handle_zoom(self, lm) -> str:
        """총모양 포즈 유지 중 엄지↔검지 tip 거리 변화로 줌인/줌아웃 판별.
        한 방향으로 여러 번 연속 발화 가능. 반대 방향은 오픈팜 전까지 차단.
        """
        dist = _thumb_index_dist(lm)
        if self._zoom_last_fired is None:
            self._zoom_last_fired = dist
            return GESTURE_NONE

        delta = dist - self._zoom_last_fired

        if delta > self._ZOOM_DELTA:
            if self._zoom_last_dir == "out":
                return GESTURE_NONE          # 방향 고정 — 차단
            self._zoom_last_dir   = "in"
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_IN

        if delta < -self._ZOOM_DELTA:
            if self._zoom_last_dir == "in":
                return GESTURE_NONE          # 방향 고정 — 차단
            self._zoom_last_dir   = "out"
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_OUT

        return GESTURE_NONE

    def _handle_volume(self, side) -> str:
        now = time.time()
        if now - self._last_volume_time < self._volume_cooldown:
            return GESTURE_NONE
        self._last_volume_time = now
        # flip 후 MediaPipe Left/Right 반전 — 물리적 오른손이 "Left"로 들어옴
        return GESTURE_VOLUME_UP if side == "Left" else GESTURE_VOLUME_DOWN

    def _reset_tracking(self):
        self._prev_drag_y       = None
        self._drag_accum        = 0.0
        self._zoom_last_fired   = None
        self._zoom_last_dir     = None
        self._pending_desire    = None
        self._pending_count     = 0
        self._window_once_fired = False
        self._palm_was_open     = False
        self._pos_history.clear()


# ── 포즈 판별 함수 (순수 함수) ───────────────────────────────────

def _fingers_up(lm) -> tuple[bool, bool, bool, bool]:
    return (
        lm[INDEX_TIP].y  < lm[INDEX_MCP].y,
        lm[MIDDLE_TIP].y < lm[MIDDLE_MCP].y,
        lm[RING_TIP].y   < lm[RING_MCP].y,
        lm[PINKY_TIP].y  < lm[PINKY_MCP].y,
    )

def _is_open_palm(lm) -> bool:
    return (
        lm[INDEX_TIP].y  < lm[INDEX_PIP].y  and
        lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y and
        lm[RING_TIP].y   < lm[RING_PIP].y   and
        lm[PINKY_TIP].y  < lm[PINKY_PIP].y
    )

def _thumb_extended(lm) -> bool:
    """엄지 L자 펴짐: THUMB_TIP ↔ INDEX_MCP 거리 > 0.13, 엄지가 검지 MCP 아래로 접히지 않음."""
    dx = lm[THUMB_TIP].x - lm[INDEX_MCP].x
    dy = lm[THUMB_TIP].y - lm[INDEX_MCP].y
    dist = (dx * dx + dy * dy) ** 0.5
    thumb_not_tucked = lm[THUMB_TIP].y < lm[INDEX_MCP].y + 0.08
    return dist > 0.13 and thumb_not_tucked

def _is_cursor(lm) -> bool:
    """검지만 펴기, 엄지 접힌 상태 (엄지 펴면 줌으로 구분)."""
    i, m, r, p = _fingers_up(lm)
    return i and not m and not r and not p and not _thumb_extended(lm)

def _is_drag_pose(lm) -> bool:
    """검지+중지 V자 — 오픈팜 제외, 엄지 접힘 필수."""
    i, m, _, _ = _fingers_up(lm)
    if not (i and m and not _is_open_palm(lm)):
        return False
    # 엄지 tip이 IP(중간 관절)보다 손목에 더 가까우면 접힌 상태
    def _d2(a, b):
        return (lm[a].x - lm[b].x)**2 + (lm[a].y - lm[b].y)**2
    return _d2(THUMB_TIP, WRIST) < _d2(THUMB_IP, WRIST)

def _is_curl(lm) -> bool:
    """손가락 오므리기: 각 손가락 tip이 PIP 관절보다 아래."""
    pairs = [
        (INDEX_TIP,  INDEX_PIP),
        (MIDDLE_TIP, MIDDLE_PIP),
        (RING_TIP,   RING_PIP),
        (PINKY_TIP,  PINKY_PIP),
    ]
    return all(lm[tip].y > lm[pip].y for tip, pip in pairs)

def _is_shaka(lm) -> bool:
    i, m, r, p = _fingers_up(lm)
    thumb_up = lm[THUMB_TIP].y < lm[INDEX_MCP].y
    return thumb_up and not i and not m and not r and p

def _palm_ref(lm) -> float:
    """손 크기 기준값: WRIST ~ MIDDLE_MCP 거리 (카메라 거리에 따라 스케일)."""
    dx = lm[WRIST].x - lm[MIDDLE_MCP].x
    dy = lm[WRIST].y - lm[MIDDLE_MCP].y
    return (dx*dx + dy*dy) ** 0.5

def _three_finger_dist(lm) -> float:
    """엄지+검지+중지 끝 3쌍 중 최대 거리 (삼각형 외접원 지름 근사)."""
    pts = [lm[THUMB_TIP], lm[INDEX_TIP], lm[MIDDLE_TIP]]
    max_d = 0.0
    for i in range(3):
        for j in range(i + 1, 3):
            dx = pts[i].x - pts[j].x
            dy = pts[i].y - pts[j].y
            d  = (dx*dx + dy*dy) ** 0.5
            if d > max_d:
                max_d = d
    return max_d


def _is_thumb_extended(lm, side: str) -> bool:
    """엄지 폄 여부 — 웹캠 x축 기준.
    flip 후 MediaPipe가 Left/Right를 내부 반전하므로 원래 조건 그대로 사용.
    오른손: tip.x > IP.x  /  왼손: tip.x < IP.x
    """
    if side == "Right":
        return lm[THUMB_TIP].x > lm[THUMB_IP].x
    else:
        return lm[THUMB_TIP].x < lm[THUMB_IP].x

def _thumb_index_dist(lm) -> float:
    """엄지 끝 ↔ 검지 끝 거리 (정규화 좌표)."""
    dx = lm[THUMB_TIP].x - lm[INDEX_TIP].x
    dy = lm[THUMB_TIP].y - lm[INDEX_TIP].y
    return (dx * dx + dy * dy) ** 0.5

def _is_gun_pose(lm, side: str) -> bool:
    """줌 진입 포즈: 엄지 완전 폄 + 검지 어느정도 세움 + 나머지 3개 접힘."""
    _, m, r, p = _fingers_up(lm)
    index_up = lm[INDEX_TIP].y < lm[INDEX_MCP].y
    return _is_thumb_extended(lm, side) and index_up and not m and not r and not p

def _is_three_finger_spread(lm) -> bool:
    """줌 진입: 엄지+검지+중지 세손가락이 충분히 벌어진 상태(측면 자세).
    - 세 끝점 최대 거리 / 손 기준값 >= 0.70 (충분한 펼침)
    - 검지·중지 끝이 PIP 위
    - 엄지가 INDEX_MCP에서 멀리 펴짐
    - 약지·새끼는 PIP 아래 (오픈팜과 구분)
    """
    ref = _palm_ref(lm)
    if ref < 1e-6:
        return False
    if _three_finger_dist(lm) / ref < 0.70:
        return False
    index_up   = lm[INDEX_TIP].y  < lm[INDEX_PIP].y
    middle_up  = lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y
    ring_down  = lm[RING_TIP].y   > lm[RING_PIP].y
    pinky_down = lm[PINKY_TIP].y  > lm[PINKY_PIP].y
    dx = lm[THUMB_TIP].x - lm[INDEX_MCP].x
    dy = lm[THUMB_TIP].y - lm[INDEX_MCP].y
    thumb_far  = (dx*dx + dy*dy) ** 0.5 > 0.13
    return index_up and middle_up and thumb_far and ring_down and pinky_down
