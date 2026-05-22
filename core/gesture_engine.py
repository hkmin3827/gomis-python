"""
제스처 판별 엔진 — 상태 기계(State Machine) 방식.

상태 전이:
  IDLE → CURSOR / DRAG / ZOOM / VOLUME  (3 프레임 연속 포즈 유지 후 확정)
  연속 상태 → IDLE  (손바닥 펴기로만 종료, 이후 0.5 s 쿨다운)
  클릭/더블클릭: 어떤 상태에서든 즉시 발화 (오므리기 앞전에만)
  창 전환: IDLE 에서 3 프레임 확정 후 원샷 발화
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
    _CONFIRM_FRAMES = 3    # 연속 N 프레임 포즈 유지 시 상태 진입
    _IDLE_COOLDOWN  = 0.5  # 상태 종료(오픈팜) 후 새 제스처 차단 시간(초)

    def __init__(self, tracker: HandTracker):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._click_threshold = cfg["click_threshold"]
        self._tracker = tracker

        self._state = State.IDLE

        # 드래그 추적
        self._prev_drag_y: float | None = None

        # 줌 추적
        self._zoom_last_fired: float | None = None

        # 볼륨 쿨다운 (초당 최대 3회)
        self._last_volume_time = 0.0
        self._volume_cooldown  = 1.0 / 3.0

        # 클릭
        self._last_click_time  = 0.0
        self._double_click_gap = 0.4    # 더블클릭 인정 간격(초)
        self._curl_active      = False  # 오므린 채 유지 중 → 재발화 방지

        # 창 전환 쿨다운
        self._last_window_time = 0.0
        self._window_cooldown  = 1.0

        # 상태 진입 확정 (N 프레임 연속 포즈)
        self._pending_desire: str | None = None
        self._pending_count: int = 0

        # 오픈팜 후 IDLE 쿨다운
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

        # ── 클릭/더블클릭: 어떤 상태에서든 최우선 감지 ──────────
        # 오므리기가 감지되면 상태 무관하게 클릭 처리
        if _is_curl(lm):
            if not self._curl_active:
                self._curl_active = True
                now = time.time()
                gap = now - self._last_click_time
                if 0 < gap < self._double_click_gap:
                    self._last_click_time = 0.0
                    return GESTURE_DOUBLE_CLICK
                self._last_click_time = now
                return GESTURE_CLICK
            return GESTURE_NONE
        else:
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
        # 오픈팜 후 쿨다운 중 → 새 제스처 무시
        if time.time() < self._idle_cooldown_until:
            self._pending_desire = None
            self._pending_count  = 0
            return GESTURE_NONE

        # 포즈 감지 우선순위: zoom > cursor > drag > volume > window
        # zoom을 cursor보다 먼저 체크: 꼬집기 중 검지가 올라와도 zoom으로 인식
        desire: str | None = None
        if _is_zoom_entry(lm, frame_w, frame_h):
            desire = "zoom"
        elif _is_cursor(lm):
            desire = "cursor"
        elif _is_drag_pose(lm):
            desire = "drag"
        elif _is_shaka(lm):
            desire = "volume"
        elif _is_window_pose(lm):
            desire = "window"

        if desire is None:
            self._pending_desire = None
            self._pending_count  = 0
            return GESTURE_NONE

        # 포즈 확정 누적 (다른 포즈로 바뀌면 리셋)
        if desire == self._pending_desire:
            self._pending_count += 1
        else:
            self._pending_desire = desire
            self._pending_count  = 1

        if self._pending_count < self._CONFIRM_FRAMES:
            return GESTURE_NONE  # 아직 확정 안 됨 — 손 준비 시간

        # ── N 프레임 확정: 상태 진입 ─────────────────────────────
        self._pending_desire = None
        self._pending_count  = 0

        if desire == "zoom":
            self._state = State.ZOOM
            self._zoom_last_fired = self._tracker.pinch_distance(lm, frame_w, frame_h)
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

        if desire == "window":
            now = time.time()
            if now - self._last_window_time > self._window_cooldown:
                self._last_window_time = now
                return GESTURE_WINDOW_RIGHT if side == "Right" else GESTURE_WINDOW_LEFT

        return GESTURE_NONE

    def _handle_drag(self, lm, frame_h) -> str:
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
        # 기준 거리는 발화 시에만 업데이트 (노이즈 방지)
        if delta > 20:
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_IN
        if delta < -20:
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_OUT
        return GESTURE_NONE

    def _handle_volume(self, side) -> str:
        now = time.time()
        if now - self._last_volume_time < self._volume_cooldown:
            return GESTURE_NONE
        self._last_volume_time = now
        return GESTURE_VOLUME_UP if side == "Right" else GESTURE_VOLUME_DOWN

    def _reset_tracking(self):
        self._prev_drag_y     = None
        self._zoom_last_fired = None
        self._pending_desire  = None
        self._pending_count   = 0


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
    """손가락 오므리기: 검지~새끼 끝이 모두 PIP 관절보다 아래."""
    pairs = [
        (INDEX_TIP,  INDEX_PIP),
        (MIDDLE_TIP, MIDDLE_PIP),
        (RING_TIP,   RING_PIP),
        (PINKY_TIP,  PINKY_PIP),
    ]
    return all(lm[tip].y > lm[pip].y for tip, pip in pairs)

def _is_shaka(lm) -> bool:
    """샤카 (엄지+새끼만 펴기): 볼륨 제스처."""
    i, m, r, p = _fingers_up(lm)
    thumb_up = lm[THUMB_TIP].y < lm[INDEX_MCP].y
    return thumb_up and not i and not m and not r and p

def _is_zoom_entry(lm, frame_w: int, frame_h: int) -> bool:
    """
    엄지+검지 꼬집기 (줌 진입).
    거리 < 프레임 폭의 12 %, 중지·약지·새끼는 접혀 있어야 함.
    임계값을 기존 4 %→12 %로 올려 실제 꼬집기 범위를 현실적으로 조정.
    """
    tx = int(lm[THUMB_TIP].x * frame_w)
    ty = int(lm[THUMB_TIP].y * frame_h)
    ix = int(lm[INDEX_TIP].x * frame_w)
    iy = int(lm[INDEX_TIP].y * frame_h)
    dist = float(np.hypot(tx - ix, ty - iy))
    if dist >= 0.12 * frame_w:
        return False
    middle_curled = lm[MIDDLE_TIP].y > lm[MIDDLE_PIP].y
    ring_curled   = lm[RING_TIP].y   > lm[RING_PIP].y
    pinky_curled  = lm[PINKY_TIP].y  > lm[PINKY_PIP].y
    return middle_curled and ring_curled and pinky_curled

def _is_window_pose(lm) -> bool:
    """
    창 전환 포즈: 손이 가로 방향 + 손가락 끝 높이가 비슷.
    - 손목(0)→중지MCP(9) 벡터 수평각 55° 이하  (기존 40°에서 완화)
    - 손가락 끝 Y 편차 0.20 이하               (기존 0.12에서 완화)
    """
    wx, wy = lm[WRIST].x, lm[WRIST].y
    mx, my = lm[MIDDLE_MCP].x, lm[MIDDLE_MCP].y
    dx, dy = mx - wx, my - wy
    if abs(dx) < 1e-6:
        return False
    angle = abs(np.degrees(np.arctan2(abs(dy), abs(dx))))
    if angle > 55:
        return False
    tips_y = [lm[INDEX_TIP].y, lm[MIDDLE_TIP].y, lm[RING_TIP].y, lm[PINKY_TIP].y]
    spread = max(tips_y) - min(tips_y)
    return spread < 0.20
