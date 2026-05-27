import json
from pathlib import Path
import pyautogui
from core.gesture_engine import GESTURE_DRAG_UP, GESTURE_DRAG_DOWN

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

pyautogui.PAUSE = 0


class ScrollController:
    def __init__(self):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)["gesture"]
        self._default_speed = cfg.get("scroll_speed", 40)
        self._settings: dict | None = None

    def set_settings(self, settings: dict):
        self._settings = settings

    def handle(self, gesture: str):
        speed = self._settings["scroll_speed"] if self._settings else self._default_speed
        if gesture == GESTURE_DRAG_UP:
            pyautogui.scroll(speed)
        elif gesture == GESTURE_DRAG_DOWN:
            pyautogui.scroll(-speed)
