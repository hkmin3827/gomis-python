import pyautogui
from core.gesture_engine import GESTURE_WINDOW_RIGHT, GESTURE_WINDOW_LEFT

pyautogui.PAUSE = 0


class WindowSwitcher:
    def handle(self, gesture: str):
        """
        오른손 → Alt+Tab (다음 창)
        왼손  → Alt+Shift+Tab (이전 창)
        """
        if gesture == GESTURE_WINDOW_RIGHT:
            pyautogui.hotkey("alt", "tab")
        elif gesture == GESTURE_WINDOW_LEFT:
            pyautogui.hotkey("alt", "shift", "tab")
