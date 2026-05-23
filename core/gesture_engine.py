"""
제스처 판별 엔진 — 상태 기계(State Machine) 방식.

상태 전이:
  IDLE → CURSOR / DRAG / ZOOM / VOLUME  (3 프레임 연속 포즈 유지 후 확정)
  연속 상태 → IDLE  (손바닥 펴기로만 종료, 이후 0.5 s 쿨다운)
  클릭/더블클릭: 어떤 상태에서든 즉시 발화 (오므리기 앞전에만)
  창 전환: 오픈팜 + 수평 스와이프 (상태 무관, 방향만으로 판별)
"""

import json
import time
from enum import Enum
from pathlib import Path

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
GESTURE_WINDOW_RIGHT  = "window_right"   # 다음 창 (오른쪽 스와이프)
GESTURE_WINDOW_LEFT   = "window_left"    # 이전 창 (왼쪽 스와이프)


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

        # 드래그 추적 — Y 이동량 누적 후 비례 스크롤
        self._prev_drag_y: float | None = None
        self._drag_accum:  float        = 0.0
        self._DRAG_STEP                 = 5

        # 줌 추적 — 오픈팜 전까지 방향 전환 완전 차단
        self._zoom_last_fired: float | None = None
        self._zoom_last_dir:   str | None   = None

        # 볼륨 쿨다운 (초당 최대 3회)
        self._last_volume_time = 0.0
        self._volume_cooldown  = 1.0 / 3.0

        # 클릭 — 오픈팜 → 오므리기 순서 강제
        self._last_click_time  = 0.0
        self._double_click_gap = 0.4
        self._curl_active      = False
        self._palm_was_open    = False

        # 창 전환 — 오픈팜 + 수평 스와이프 (손 방향 무관, 이동 방향만 판별)
        self._last_window_time  = 0.0
        self._window_cooldown   = 1.0
        self._window_once_fired = False
        self._pos_history: list[tuple[float, float]] = []  # (wrist_x, timestamp)
        self._swipe_win         = 0.5    # 추적 시간 윈도우(초)
        self._swipe_dist        = 0.30   # 웹캠 너비 30% 이동 필요
        self._swipe_min_vel     = 0.20   # 최소 속도 (정규화/초)

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
        now  = time.time()

        # ── 손목 위치 이력 누적 (상태 무관) ──────────────────────
        self._pos_history = [(x, t) for x, t in self._pos_history if now - t < self._swipe_win]
        self._pos_history.append((lm[WRIST].x, now))

        # 쿨다운 만료 시 재스와이프 허용
        if self._window_once_fired and now - self._last_window_time >= self._window_cooldown:
            self._window_once_fired = False
            self._pos_history.clear()

        # ── 창 전환: 오픈팜 + 수평 스와이프 (상태 무관) ──────────
        # 오른쪽 스와이프 → 다음 창 / 왼쪽 스와이프 → 이전 창
        if _is_open_palm(lm):
            swipe = self._check_swipe()
            if swipe != GESTURE_NONE:
                return swipe

        # ── 클릭/더블클릭 ────────────────────────────────────────
        # 조건: 오픈팜 → 오므리기 순서여야 발화. ZOOM 상태에서는 차단.
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
            return self._handle_zoom(lm, frame_w, frame_h)

        if self._state == State.VOLUME:
            return self._handle_volume(side)

        # ── IDLE: 새 제스처 진입 판별 ────────────────────────────
        return self._detect_from_idle(lm, frame_w, frame_h)

    @property
    def state(self) -> str:
        return self._state.value

    # ── 내부 메서드 ───────────────────────────────────────────────

    def _detect_from_idle(self, lm, frame_w, frame_h) -> str:
        now = time.time()

        # 오픈팜 후 쿨다운 중 → 새 제스처 무시
        if now < self._idle_cooldown_until:
            self._pending_desire = None
            self._pending_count  = 0
            return GESTURE_NONE

        # 포즈 감지 우선순위: zoom > cursor > drag > volume
        desire: str | None = None
        if _is_zoom_entry(lm):
            desire = "zoom"
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

        # 포즈 확정 누적 (다른 포즈로 바뀌면 리셋)
        if desire == self._pending_desire:
            self._pending_count += 1
        else:
            self._pending_desire = desire
            self._pending_count  = 1

        confirm_needed = 1 if desire == "drag" else self._CONFIRM_FRAMES
        if self._pending_count < confirm_needed:
            return GESTURE_NONE

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

        return GESTURE_NONE

    def _check_swipe(self) -> str:
        """오픈팜 + 수평 이동 → 창 전환.
        손 방향 무관. 사람 기준 오른쪽 스와이프(웹캠 x 감소) → 다음 창.
        """
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
            # 카메라 좌우반전: displacement < 0 → 사람이 오른쪽으로 스와이프한 것
            is_right_swipe = displacement < 0
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

    def _handle_zoom(self, lm, frame_w, frame_h) -> str:
        dist = self._tracker.pinch_distance(lm, frame_w, frame_h)
        if self._zoom_last_fired is None:
            self._zoom_last_fired = dist
            return GESTURE_NONE
        delta = dist - self._zoom_last_fired

        if delta > 20:
            if self._zoom_last_dir == "out":
                return GESTURE_NONE
            self._zoom_last_dir   = "in"
            self._zoom_last_fired = dist
            return GESTURE_ZOOM_IN

        if delta < -20:
            if self._zoom_last_dir == "in":
                return GESTURE_NONE
            self._zoom_last_dir   = "out"
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
    """(index, middle, ring, pinky) 각각 펴져 있는지."""
    return (
        lm[INDEX_TIP].y  < lm[INDEX_MCP].y,
        lm[MIDDLE_TIP].y < lm[MIDDLE_MCP].y,
        lm[RING_TIP].y   < lm[RING_MCP].y,
        lm[PINKY_TIP].y  < lm[PINKY_MCP].y,
    )

def _is_open_palm(lm) -> bool:
    """손바닥 펴기: 검지~새끼 끝이 모두 PIP(중간 관절) 위에 있어야 인정."""
    return (
        lm[INDEX_TIP].y  < lm[INDEX_PIP].y  and
        lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y and
        lm[RING_TIP].y   < lm[RING_PIP].y   and
        lm[PINKY_TIP].y  < lm[PINKY_PIP].y
    )

def _thumb_extended(lm) -> bool:
    """엄지가 옆으로 펴진 L자 상태."""
    dx = lm[THUMB_TIP].x - lm[INDEX_MCP].x
    dy = lm[THUMB_TIP].y - lm[INDEX_MCP].y
    dist = (dx * dx + dy * dy) ** 0.5
    thumb_not_tucked = lm[THUMB_TIP].y < lm[INDEX_MCP].y + 0.08
    return dist > 0.13 and thumb_not_tucked

def _is_cursor(lm) -> bool:
    """검지만 펴기, 엄지는 접힌 상태."""
    i, m, r, p = _fingers_up(lm)
    return i and not m and not r and not p and not _thumb_extended(lm)

def _is_drag_pose(lm) -> bool:
    """검지+중지 V자. 오픈팜과는 _is_open_palm으로 구별."""
    i, m, _, _ = _fingers_up(lm)
    return i and m and not _is_open_palm(lm)

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

def _is_zoom_entry(lm) -> bool:
    """검지+엄지 L자 포즈 (줌 진입)."""
    i, m, r, p = _fingers_up(lm)
    return i and not m and not r and not p and _thumb_extended(lm)
