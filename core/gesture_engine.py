"""
제스처 판별 엔진 — 상태 기계(State Machine) 방식.

상태 전이:
  IDLE → CURSOR / DRAG / ZOOM / VOLUME  (연속 제스처 진입)
  연속 상태 → IDLE  (손바닥 펴기로만 종료)
  원샷 제스처(CLICK, DOUBLE_CLICK, WINDOW_SWITCH)는 상태 없이 IDLE에서 즉시 발화.
"""

import json
import time
from enum import Enum
from pathlib import Path
import numpy as np

from .hand_tracker import (
    HandTracker, HandResult,
    WRIST, THUMB_TIP,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP, RING_PIP, RING_MCP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

# ── 제스처 이름 상수 ─────────────────────────────────────────────
GESTURE_NONE          = "none"
GESTURE_CURSOR        = "cursor"         # 검지만 편 상태 → 커서 이동
GESTURE_CLICK         = "click"          # 손가락 오므리기 (원샷)
GESTURE_DOUBLE_CLICK  = "double_click"   # 오므리기 2회 (원샷)
GESTURE_DRAG_UP       = "drag_up"        # V자 위로
GESTURE_DRAG_DOWN     = "drag_down"      # V자 아래로
GESTURE_ZOOM_IN       = "zoom_in"        # 엄지+검지 벌리기
GESTURE_ZOOM_OUT      = "zoom_out"       # 엄지+검지 좁히기
GESTURE_VOLUME_UP     = "volume_up"      # 오른손 샤카 (연속)
GESTURE_VOLUME_DOWN   = "volume_down"    # 왼손 샤카 (연속)
GESTURE_WINDOW_RIGHT  = "window_right"   # 오른손 창 전환
GESTURE_WINDOW_LEFT   = "window_left"    # 왼손 창 전환


# ── 상태 ─────────────────────────────────────────────────────────
class State(Enum):
    IDLE    = "idle"
    CURSOR  = "cursor"
    DRAG    = "drag"
    ZOOM    = "zoom"
    VOLUME  = "volume"


class GestureEngine:
    def __init__(self, tracker: HandTracker):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._click_threshold = cfg["click_threshold"]
        self._tracker = tracker

        self._state = State.IDLE

        # 드래그 추적
        self._prev_drag_y: float | None = None

        # 줌 추적 — 마지막 발화 시점의 거리를 기준으로 비교 (매 프레임 업데이트 안 함)
        self._zoom_last_fired: float | None = None

        # 볼륨 쿨다운 (초당 최대 3회)
        self._last_volume_time = 0.0
        self._volume_cooldown  = 1.0 / 3.0

        # 더블클릭 감지
        self._last_click_time  = 0.0
        self._double_click_gap = 0.4   # 초

        # 창 전환 쿨다운
        self._last_window_time = 0.0
        self._window_cooldown  = 1.0

    # ── 공개 메서드 ───────────────────────────────────────────────

    def detect(self, hand: HandResult | None, frame_w: int, frame_h: int) -> str:
        if hand is None:
            self._state = State.IDLE
            self._reset_tracking()
            return GESTURE_NONE

        lm = hand.landmarks
        side = hand.handedness  # "Left" or "Right"

        # 손바닥 펴기 → 연속 제스처 종료 (IDLE 복귀)
        if self._state != State.IDLE and _is_open_palm(lm):
            self._state = State.IDLE
            self._reset_tracking()
            return GESTURE_NONE

        # ── 연속 상태 처리 ────────────────────────────────────────
        if self._state == State.CURSOR:
            # 포즈 흐트러져도 손바닥 펴기 전까지 CURSOR 유지
            return GESTURE_CURSOR if _is_cursor(lm) else GESTURE_NONE

        if self._state == State.DRAG:
            return self._handle_drag(lm, frame_h)

        if self._state == State.ZOOM:
            return self._handle_zoom(lm, frame_w, frame_h)

        if self._state == State.VOLUME:
            return self._handle_volume(side)

        # ── IDLE: 새 제스처 진입 판별 ────────────────────────────
        return self._detect_from_idle(lm, side, frame_w, frame_h)

    @property
    def state(self) -> str:
        return self._state.value

    # ── 내부 메서드 ───────────────────────────────────────────────

    def _detect_from_idle(self, lm, side, frame_w, frame_h) -> str:
        # 커서: 검지만 펴기
        if _is_cursor(lm):
            self._state = State.CURSOR
            return GESTURE_CURSOR

        # 드래그: 검지+중지 V자
        if _is_drag_pose(lm):
            self._state = State.DRAG
            self._prev_drag_y = lm[INDEX_TIP].y
            return GESTURE_NONE

        # 줌: 엄지+검지 꼬집기 진입
        if _is_zoom_entry(lm, frame_w, frame_h, self._click_threshold):
            self._state = State.ZOOM
            self._zoom_last_fired = self._tracker.pinch_distance(lm, frame_w, frame_h)
            return GESTURE_NONE

        # 볼륨: 샤카 (엄지+새끼)
        if _is_shaka(lm):
            self._state = State.VOLUME
            return GESTURE_NONE

        # 클릭 / 더블클릭: 손가락 오므리기
        if _is_curl(lm):
            now = time.time()
            if now - self._last_click_time < self._double_click_gap:
                self._last_click_time = 0.0
                return GESTURE_DOUBLE_CLICK
            self._last_click_time = now
            return GESTURE_CLICK

        # 창 전환: 가로 방향 + 손가락 모음
        if _is_window_pose(lm):
            now = time.time()
            if now - self._last_window_time > self._window_cooldown:
                self._last_window_time = now
                return GESTURE_WINDOW_RIGHT if side == "Right" else GESTURE_WINDOW_LEFT

        return GESTURE_NONE

    def _handle_drag(self, lm, frame_h) -> str:
        # 포즈 흐트러져도 손바닥 펴기 전까지 DRAG 상태 유지
        if not _is_drag_pose(lm):
            return GESTURE_NONE
        curr_y = lm[INDEX_TIP].y
        if self._prev_drag_y is None:
            self._prev_drag_y = curr_y
            return GESTURE_NONE
        delta = (curr_y - self._prev_drag_y) * frame_h
        self._prev_drag_y = curr_y
        if delta < -8:
            return GESTURE_DRAG_UP
        if delta > 8:
            return GESTURE_DRAG_DOWN
        return GESTURE_NONE

    def _handle_zoom(self, lm, frame_w, frame_h) -> str:
        dist = self._tracker.pinch_distance(lm, frame_w, frame_h)
        if self._zoom_last_fired is None:
            self._zoom_last_fired = dist
            return GESTURE_NONE
        delta = dist - self._zoom_last_fired
        # 발화 기준거리는 실제 제스처가 발화될 때만 업데이트 (노이즈 방지)
        if delta > 25:
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_IN
        if delta < -25:
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_OUT
        return GESTURE_NONE

    def _handle_volume(self, side) -> str:
        now = time.time()
        if now - self._last_volume_time < self._volume_cooldown:
            return GESTURE_NONE
        self._last_volume_time = now
        return GESTURE_VOLUME_UP if side == "Right" else GESTURE_VOLUME_DOWN

    def _exit_to_idle(self) -> str:
        self._state = State.IDLE
        self._reset_tracking()
        return GESTURE_NONE

    def _reset_tracking(self):
        self._prev_drag_y    = None
        self._zoom_last_fired = None


# ── 포즈 판별 함수 (순수 함수) ───────────────────────────────────

def _fingers_up(lm) -> tuple[bool, bool, bool, bool]:
    """(index, middle, ring, pinky) 각각 펴져 있는지."""
    return (
        lm[INDEX_TIP].y  < lm[INDEX_MCP].y,
        lm[MIDDLE_TIP].y < lm[MIDDLE_MCP].y,
        lm[RING_TIP].y   < lm[RING_MCP].y,
        lm[PINKY_TIP].y  < lm[PINKY_MCP].y,
    )

def _is_open_palm(lm) -> bool:
    """손바닥 펴기: 검지~새끼 모두 펴진 상태."""
    i, m, r, p = _fingers_up(lm)
    return i and m and r and p

def _is_cursor(lm) -> bool:
    """검지만 펴기."""
    i, m, r, p = _fingers_up(lm)
    return i and not m and not r and not p

def _is_drag_pose(lm) -> bool:
    """검지+중지만 펴기 (V자)."""
    i, m, r, p = _fingers_up(lm)
    return i and m and not r and not p

def _is_curl(lm) -> bool:
    """손가락 오므리기: 검지~새끼 끝이 모두 PIP 관절보다 아래 (구부러짐)."""
    pairs = [
        (INDEX_TIP, INDEX_PIP),
        (MIDDLE_TIP, MIDDLE_PIP),
        (RING_TIP, RING_PIP),
        (PINKY_TIP, PINKY_PIP),
    ]
    return all(lm[tip].y > lm[pip].y for tip, pip in pairs)

def _is_shaka(lm) -> bool:
    """샤카 (엄지+새끼만 펴기): 볼륨 제스처."""
    i, m, r, p = _fingers_up(lm)
    # 엄지: tip이 검지 MCP보다 멀리 있으면 펴진 것으로 간주
    thumb_up = lm[THUMB_TIP].y < lm[INDEX_MCP].y
    return thumb_up and not i and not m and not r and p

def _is_zoom_entry(lm, frame_w, frame_h, threshold) -> bool:
    """엄지+검지 꼬집기 (줌 진입): 중지·약지·새끼는 반드시 접혀 있어야 함."""
    tx = int(lm[THUMB_TIP].x * frame_w)
    ty = int(lm[THUMB_TIP].y * frame_h)
    ix = int(lm[INDEX_TIP].x * frame_w)
    iy = int(lm[INDEX_TIP].y * frame_h)
    dist = float(np.hypot(tx - ix, ty - iy))
    if dist >= threshold * frame_w:
        return False
    # 중지·약지·새끼가 접혀 있어야만 줌 진입 허용 (드래그 V자와 구분)
    middle_curled = lm[MIDDLE_TIP].y > lm[MIDDLE_PIP].y
    ring_curled   = lm[RING_TIP].y   > lm[RING_PIP].y
    pinky_curled  = lm[PINKY_TIP].y  > lm[PINKY_PIP].y
    return middle_curled and ring_curled and pinky_curled

def _is_window_pose(lm) -> bool:
    """
    창 전환 포즈: 손이 가로 방향 + 손가락 모음.
    - 손목(0)→중지MCP(9) 벡터가 수평에 가까울 것
    - 손가락 끝들의 y 편차가 작을 것 (나란히 정렬)
    """
    wx, wy = lm[WRIST].x, lm[WRIST].y
    mx, my = lm[MIDDLE_MCP].x, lm[MIDDLE_MCP].y
    dx, dy = mx - wx, my - wy
    if abs(dx) < 1e-6:
        return False
    angle = abs(np.degrees(np.arctan2(abs(dy), abs(dx))))
    if angle > 40:          # 40도 초과 → 세로 방향
        return False

    # 손가락 끝 y 편차 확인 (모두 비슷한 높이)
    tips_y = [lm[INDEX_TIP].y, lm[MIDDLE_TIP].y, lm[RING_TIP].y, lm[PINKY_TIP].y]
    spread = max(tips_y) - min(tips_y)
    return spread < 0.12    # 정규화 좌표 기준
