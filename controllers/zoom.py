import pyautogui
from core.gesture_engine import GESTURE_ZOOM_IN, GESTURE_ZOOM_OUT

pyautogui.PAUSE = 0


class ZoomController:
    def handle(self, gesture: str):
        """
        Ctrl+휠 방식으로 줌 인/아웃.
        브라우저, 탐색기, Office 등 대부분의 앱에서 동작.
        """
        if gesture == GESTURE_ZOOM_IN:
            pyautogui.hotkey("ctrl", "equal")   # Ctrl++
        elif gesture == GESTURE_ZOOM_OUT:
            pyautogui.hotkey("ctrl", "minus")   # Ctrl+-
