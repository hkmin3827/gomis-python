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
GESTURE_WINDOW_ALT_START_RIGHT = "window_alt_start_right"
GESTURE_WINDOW_ALT_START_LEFT  = "window_alt_start_left"
GESTURE_WINDOW_ALT_TAB         = "window_alt_tab"
GESTURE_WINDOW_ALT_END         = "window_alt_end"

GESTURE_VOICE_START = "voice_start"
GESTURE_VOICE_END   = "voice_end"


class State(Enum):
    IDLE    = "idle"
    CURSOR  = "cursor"
    DRAG    = "drag"
    ZOOM    = "zoom"
    VOLUME  = "volume"
    ALT_TAB = "alt_tab"


class GestureEngine:
    _CONFIRM_FRAMES = 3
    _IDLE_COOLDOWN  = 0.5

    _ZOOM_DELTA      = 0.03   # 기준 거리에서 이 이상 벌어지거나 좁혀지면 연속 발화
    _DRAG_THRESHOLD  = 0.05   # 기준 Y에서 이 이상 벗어나면 연속 발화 (정규화 좌표)

    def __init__(self, tracker: HandTracker):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._click_threshold = cfg["click_threshold"]
        self._tracker = tracker

        self._state = State.IDLE

        # 드래그 — 진입 시 기준 Y 고정, 위/아래 유지 시 연속 발화
        self._drag_baseline_y: float | None = None

        # 줌 — 진입 시 기준거리 고정, 매 프레임 연속 발화
        self._zoom_baseline: float | None = None   # 진입 시 기준 거리
        self._zoom_last_dir: str | None   = None   # "in" | "out"

        # 볼륨
        self._last_volume_time = 0.0
        self._volume_cooldown  = 1.0 / 3.0

        # 클릭
        self._last_click_time  = 0.0
        self._double_click_gap = 0.4
        self._curl_active      = False
        self._palm_was_open    = False

        # 창 전환 (스와이프 감지)
        self._pos_history: list[tuple[float, float]] = []
        self._swipe_win         = 0.5
        self._swipe_dist        = 0.30
        self._swipe_min_vel     = 0.20

        # Alt+Tab 홀드 모드
        self._alt_tab_dir:       str | None = None   # "right" | "left"
        self._last_alt_tab_tick: float      = 0.0
        self._alt_tab_interval:  float      = 0.5

        # 양손 박수 감지 (음성 타이핑)
        self._clap_state:        str   = "apart"   # "apart" | "together"
        self._clap_apart_time:   float = 0.0
        self._clap_together_time: float = 0.0
        self._clap_count:        int   = 0

        # 상태 진입 확정
        self._pending_desire: str | None = None
        self._pending_count: int = 0
        self._idle_cooldown_until: float = 0.0


    def detect(self, hand: HandResult | None, frame_w: int, frame_h: int) -> str:
        if hand is None:
            if self._state == State.ALT_TAB:
                self._state = State.IDLE
                self._reset_tracking()
                return GESTURE_WINDOW_ALT_END
            self._state = State.IDLE
            self._reset_tracking()
            self._curl_active = False
            return GESTURE_NONE

        lm   = hand.landmarks
        side = hand.handedness
        now  = time.time()

        # 손목 위치 누적
        self._pos_history = [(x, t) for x, t in self._pos_history if now - t < self._swipe_win]
        self._pos_history.append((lm[WRIST].x, now))

        # Alt+Tab 홀드 상태 — 주먹으로만 종료
        if self._state == State.ALT_TAB:
            return self._handle_alt_tab(lm, now)

        # 창 전환: 오픈팜 + 수평 스와이프 → Alt+Tab 홀드 진입
        if _is_open_palm(lm):
            swipe_dir = self._check_swipe_dir()
            if swipe_dir is not None:
                self._state = State.ALT_TAB
                self._alt_tab_dir = swipe_dir
                self._last_alt_tab_tick = now
                return (GESTURE_WINDOW_ALT_START_RIGHT if swipe_dir == "right"
                        else GESTURE_WINDOW_ALT_START_LEFT)

        # 클릭/더블클릭 (ZOOM 상태 제외) 
        is_open = _is_open_palm(lm)
        is_curl = _is_curl(lm)

        if is_open:
            self._palm_was_open = True
            self._curl_active   = False

        if is_curl and self._state not in (State.ZOOM, State.DRAG):
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

        # 손바닥 펴기 → 연속 제스처 종료 
        if self._state != State.IDLE and _is_open_palm(lm):
            self._state = State.IDLE
            self._reset_tracking()
            self._idle_cooldown_until = time.time() + self._IDLE_COOLDOWN
            return GESTURE_NONE

        # 연속 상태 처리 
        if self._state == State.CURSOR:
            return GESTURE_CURSOR if _is_cursor(lm) else GESTURE_NONE

        if self._state == State.DRAG:
            return self._handle_drag(lm)

        if self._state == State.ZOOM:
            return self._handle_zoom(lm)

        if self._state == State.VOLUME:
            return self._handle_volume(side)

        return self._detect_from_idle(lm, side, frame_w, frame_h)

    @property
    def state(self) -> str:
        return self._state.value



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

        confirm_needed = 1 if desire in ("drag", "cursor") else self._CONFIRM_FRAMES
        if self._pending_count < confirm_needed:
            return GESTURE_NONE

        self._pending_desire = None
        self._pending_count  = 0

        if desire == "zoom_gun":
            self._state = State.ZOOM
            self._zoom_baseline = _thumb_index_dist(lm)
            self._zoom_last_dir = None
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

    def _check_swipe_dir(self) -> str | None:
        """스와이프 방향 감지. 감지 시 history 초기화. "right"/"left"/None 반환."""
        if len(self._pos_history) < 5:
            return None
        xs = [x for x, _ in self._pos_history]
        ts = [t for _, t in self._pos_history]
        displacement = xs[-1] - xs[0]
        duration = max(ts[-1] - ts[0], 1e-6)
        velocity = displacement / duration
        if abs(velocity) > self._swipe_min_vel and abs(displacement) > self._swipe_dist:
            self._pos_history.clear()
            return "right" if displacement > 0 else "left"
        return None

    def _handle_alt_tab(self, lm, now: float) -> str:
        """Alt 홀드 중: 주먹 → Alt 해제, 1초마다 Tab 발화."""
        if _is_curl(lm):
            self._state = State.IDLE
            self._reset_tracking()
            self._idle_cooldown_until = now + self._IDLE_COOLDOWN
            return GESTURE_WINDOW_ALT_END
        if now - self._last_alt_tab_tick >= self._alt_tab_interval:
            self._last_alt_tab_tick = now
            return GESTURE_WINDOW_ALT_TAB
        return GESTURE_NONE

    def _handle_drag(self, lm) -> str:
        """진입 시 기준 Y 고정 — 기준보다 위면 DRAG_UP, 아래면 DRAG_DOWN 연속 발화."""
        curr_y = lm[INDEX_TIP].y
        if self._drag_baseline_y is None:
            self._drag_baseline_y = curr_y
            return GESTURE_NONE

        delta = curr_y - self._drag_baseline_y
        if delta < -self._DRAG_THRESHOLD:
            return GESTURE_DRAG_UP
        if delta > self._DRAG_THRESHOLD:
            return GESTURE_DRAG_DOWN
        return GESTURE_NONE

    def _handle_zoom(self, lm) -> str:
        """총모양 유지 중 엄지↔검지 기준거리 대비 변화로 방향 판별.
        벌어진 상태 → ZOOM_IN 매 프레임 발화 / 좁혀진 상태 → ZOOM_OUT 매 프레임 발화.
        반대 방향 전환은 오픈팜 전까지 차단.
        """
        if self._zoom_baseline is None:
            return GESTURE_NONE

        delta = _thumb_index_dist(lm) - self._zoom_baseline

        if delta > self._ZOOM_DELTA:
            if self._zoom_last_dir == "out":
                return GESTURE_NONE
            self._zoom_last_dir = "in"
            return GESTURE_ZOOM_IN

        if delta < -self._ZOOM_DELTA:
            if self._zoom_last_dir == "in":
                return GESTURE_NONE
            self._zoom_last_dir = "out"
            return GESTURE_ZOOM_OUT

        return GESTURE_NONE

    def _handle_volume(self, side) -> str:
        now = time.time()
        if now - self._last_volume_time < self._volume_cooldown:
            return GESTURE_NONE
        self._last_volume_time = now
        # flip 후 MediaPipe Left/Right 반전 — 물리적 오른손이 "Left"로 들어옴
        return GESTURE_VOLUME_UP if side == "Left" else GESTURE_VOLUME_DOWN

    def detect_clap(self, hands: list) -> str | None:
        """양손 박수 감지.
        두 손 모두 오픈팜 + 손목 거리 < 0.35 → 박수.
        홀수 번째 박수 → GESTURE_VOICE_START, 짝수 번째 → GESTURE_VOICE_END.
        """
        now = time.time()

        if len(hands) < 2:
            if self._clap_state == "together":
                self._clap_state = "apart"
                self._clap_apart_time = now
            return None

        h1, h2 = hands[0], hands[1]
        # 양손 모두 오픈팜 + 정면도 >= 0.4 (손날/측면 오인식 방어)
        both_open = (
            _is_open_palm(h1.landmarks) and _palm_facing_ratio(h1.landmarks) >= 0.4 and
            _is_open_palm(h2.landmarks) and _palm_facing_ratio(h2.landmarks) >= 0.4
        )

        dx = h1.landmarks[WRIST].x - h2.landmarks[WRIST].x
        dy = h1.landmarks[WRIST].y - h2.landmarks[WRIST].y
        dist = (dx * dx + dy * dy) ** 0.5

        together = both_open and dist < 0.35

        if together and self._clap_state == "apart":
            if now - self._clap_apart_time > 0.3:  # 연속 오인식 방지
                self._clap_state = "together"
                self._clap_together_time = now
                self._clap_count += 1
                return GESTURE_VOICE_START if self._clap_count % 2 == 1 else GESTURE_VOICE_END

        elif not together and self._clap_state == "together":
            if now - self._clap_together_time > 0.15:
                self._clap_state = "apart"
                self._clap_apart_time = now

        return None

    def _reset_tracking(self):
        self._drag_baseline_y  = None
        self._zoom_baseline    = None
        self._zoom_last_dir    = None
        self._pending_desire   = None
        self._pending_count    = 0
        self._palm_was_open    = False
        self._zoom_last_dir    = None
        self._alt_tab_dir      = None
        self._last_alt_tab_tick = 0.0
        self._pos_history.clear()


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
    """검지+중지 V자. 손 정면도 >= 0.5 (45° 이내) + 엄지 접힘 필수."""
    if _palm_facing_ratio(lm) < 0.5:   # 45° 기준 — 너무 옆이면 drag 불가
        return False
    index_up  = lm[INDEX_TIP].y  < lm[INDEX_PIP].y
    middle_up = lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y
    if not (index_up and middle_up and not _is_open_palm(lm)):
        return False
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

def _lm_dist(lm, a: int, b: int) -> float:
    """두 랜드마크 간 2D 거리."""
    dx = lm[a].x - lm[b].x
    dy = lm[a].y - lm[b].y
    return (dx*dx + dy*dy) ** 0.5

def _palm_facing_ratio(lm) -> float:
    """정면도 비율: INDEX_MCP~PINKY_MCP x너비 / 손바닥 기준값.
    1에 가까울수록 정면, 0에 가까울수록 측면. 45° ≈ 0.5.
    """
    width = abs(lm[INDEX_MCP].x - lm[PINKY_MCP].x)
    ref = _palm_ref(lm)
    return width / ref if ref > 1e-6 else 0.0

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
    """줌 진입: 엄지 폄 + 검지 세움 + 나머지 접힘 + 손 측면도 >= 0.5 (45° 기준).
    curl 검사는 거리 기반 — y좌표 방식은 손 기울기에 취약하므로 사용 안 함.
    """
    if _palm_facing_ratio(lm) >= 0.5:  # 45° 기준 — 너무 정면이면 zoom 불가
        return False
    index_up = lm[INDEX_TIP].y < lm[INDEX_MCP].y
    if not _is_thumb_extended(lm, side) or not index_up:
        return False
    ref = _palm_ref(lm)
    middle_curled = _lm_dist(lm, MIDDLE_TIP, MIDDLE_MCP) < ref * 0.85
    ring_curled   = _lm_dist(lm, RING_TIP,   RING_MCP)   < ref * 0.85
    pinky_curled  = _lm_dist(lm, PINKY_TIP,  PINKY_MCP)  < ref * 0.85
    return middle_curled and ring_curled and pinky_curled

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
