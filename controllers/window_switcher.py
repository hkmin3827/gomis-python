import pyautogui
from core.gesture_engine import GESTURE_WINDOW_RIGHT, GESTURE_WINDOW_LEFT

pyautogui.PAUSE = 0


class WindowSwitcher:
    def handle(self, gesture: str):
        if gesture == GESTURE_WINDOW_RIGHT:
            pyautogui.hotkey("alt", "tab")
        elif gesture == GESTURE_WINDOW_LEFT:
            pyautogui.hotkey("alt", "shift", "tab")
