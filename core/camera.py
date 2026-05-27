import cv2
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"


class Camera:
    def __init__(self):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)["camera"]
        self.index = cfg["index"]
        self.width = cfg["width"]
        self.height = cfg["height"]
        self.fps = cfg["fps"]
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(self.index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not self._cap.isOpened():
            raise RuntimeError(f"카메라 {self.index}번을 열 수 없습니다.")

    def read(self):
        """(success: bool, frame: ndarray) 반환. frame은 BGR 포맷 (좌우 반전 적용)."""
        ok, frame = self._cap.read()
        if ok:
            frame = cv2.flip(frame, 1)
        return ok, frame

    def close(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()
