import json
from pathlib import Path
import pyautogui
from core.gesture_engine import GESTURE_DRAG_UP, GESTURE_DRAG_DOWN

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

pyautogui.PAUSE = 0


class ScrollController:
    def __init__(self):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))["gesture"]
        self._speed = cfg["scroll_speed"]

    def handle(self, gesture: str):
        if gesture == GESTURE_DRAG_UP:
            pyautogui.scroll(self._speed)
        elif gesture == GESTURE_DRAG_DOWN:
            pyautogui.scroll(-self._speed)
