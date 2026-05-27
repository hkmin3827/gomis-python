import json
from collections import namedtuple
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np
from resource_path import resource_path

CONFIG_PATH = resource_path('config', 'settings.json')
MODEL_PATH  = resource_path('core', 'hand_landmarker.task')

# 랜드마크 인덱스
WRIST      = 0
THUMB_TIP  = 4; THUMB_IP = 3
INDEX_TIP  = 8;  INDEX_PIP  = 6;  INDEX_MCP  = 5
MIDDLE_TIP = 12; MIDDLE_PIP = 10; MIDDLE_MCP = 9
RING_TIP   = 16; RING_PIP   = 14; RING_MCP   = 13
PINKY_TIP  = 20; PINKY_PIP  = 18; PINKY_MCP  = 17

CONNECTIONS = mp_vision.HandLandmarksConnections.HAND_CONNECTIONS

HandResult = namedtuple("HandResult", ["landmarks", "handedness"])  # handedness: "Left" | "Right"


class HandTracker:
    def __init__(self):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        sensitivity = cfg["sensitivity"]

        base_options = mp_python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,                               # 양손 감지 (창 전환·볼륨 구분용)
            min_hand_detection_confidence=sensitivity,
            min_hand_presence_confidence=sensitivity,
            min_tracking_confidence=sensitivity,
        )
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
        self._timestamp_ms = 0

    def process_all(self, frame_bgr) -> list:
        """BGR 프레임 → 감지된 모든 HandResult 리스트 (0~2개). 프레임당 1회 호출."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._timestamp_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.hand_landmarks:
            return []

        hands = []
        for i, lm in enumerate(result.hand_landmarks):
            side = result.handedness[i][0].category_name if result.handedness else "Right"
            hands.append(HandResult(lm, side))
        return hands

    def process(self, frame_bgr) -> HandResult | None:
        """BGR 프레임 → 첫 번째 HandResult. 손 없으면 None."""
        hands = self.process_all(frame_bgr)
        return hands[0] if hands else None

    def draw(self, frame_bgr, landmarks):
        h, w = frame_bgr.shape[:2]
        for conn in CONNECTIONS:
            a, b = conn.start, conn.end
            ax, ay = int(landmarks[a].x * w), int(landmarks[a].y * h)
            bx, by = int(landmarks[b].x * w), int(landmarks[b].y * h)
            cv2.line(frame_bgr, (ax, ay), (bx, by), (0, 200, 0), 2)
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame_bgr, (cx, cy), 4, (0, 0, 255), -1)

    def get_tip(self, landmarks, index: int, frame_w: int, frame_h: int):
        lm = landmarks[index]
        return int(lm.x * frame_w), int(lm.y * frame_h)

    def pinch_distance(self, landmarks, frame_w: int, frame_h: int) -> float:
        tx, ty = self.get_tip(landmarks, THUMB_TIP, frame_w, frame_h)
        ix, iy = self.get_tip(landmarks, INDEX_TIP, frame_w, frame_h)
        return float(np.hypot(tx - ix, ty - iy))

    def is_finger_up(self, landmarks, tip_idx: int, mcp_idx: int) -> bool:
        return landmarks[tip_idx].y < landmarks[mcp_idx].y

    def close(self):
        self._landmarker.close()
