import ctypes
from core.gesture_engine import GESTURE_WINDOW_RIGHT, GESTURE_WINDOW_LEFT

_KEYEVENTF_KEYUP = 0x0002
_VK_MENU  = 0x12   # Alt
_VK_TAB   = 0x09   # Tab
_VK_SHIFT = 0x10   # Shift


def _alt_tab(shift: bool = False):
    """ctypes keybd_event로 Alt(+Shift)+Tab 전송 — pyautogui보다 신뢰성 높음."""
    kbe = ctypes.windll.user32.keybd_event
    if shift:
        kbe(_VK_SHIFT, 0, 0, 0)
    kbe(_VK_MENU, 0, 0, 0)
    kbe(_VK_TAB,  0, 0, 0)
    kbe(_VK_TAB,  0, _KEYEVENTF_KEYUP, 0)
    kbe(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    if shift:
        kbe(_VK_SHIFT, 0, _KEYEVENTF_KEYUP, 0)


class WindowSwitcher:
    def handle(self, gesture: str):
        if gesture == GESTURE_WINDOW_RIGHT:
            _alt_tab(shift=False)
        elif gesture == GESTURE_WINDOW_LEFT:
            _alt_tab(shift=True)
