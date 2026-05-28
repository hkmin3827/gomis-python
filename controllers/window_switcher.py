import ctypes
from core.gesture_engine import (
    GESTURE_WINDOW_ALT_START_RIGHT, GESTURE_WINDOW_ALT_START_LEFT,
    GESTURE_WINDOW_ALT_TAB, GESTURE_WINDOW_ALT_END,
)

_KEYEVENTF_KEYUP = 0x0002
_VK_MENU  = 0x12   # Alt
_VK_TAB   = 0x09   # Tab
_VK_SHIFT = 0x10   # Shift


def _press(vk):   ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
def _release(vk): ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


class WindowSwitcher:
    def __init__(self):
        self._alt_held   = False
        self._shift_held = False

    def handle(self, gesture: str):
        if gesture == GESTURE_WINDOW_ALT_START_RIGHT:
            self._start(shift=True)
        elif gesture == GESTURE_WINDOW_ALT_START_LEFT:
            self._start(shift=False)
        elif gesture == GESTURE_WINDOW_ALT_TAB:
            self._tap_tab()
        elif gesture == GESTURE_WINDOW_ALT_END:
            self._release()

    def force_release(self):
        """앱 종료 시 Alt 키 강제 해제."""
        if self._alt_held:
            self._release()

    def _start(self, shift: bool):
        if self._alt_held:
            self._release()
        if shift:
            _press(_VK_SHIFT)
            self._shift_held = True
        _press(_VK_MENU)        # Alt 홀드
        self._alt_held = True
        _press(_VK_TAB)         # 첫 Tab
        _release(_VK_TAB)

    def _tap_tab(self):
        if not self._alt_held:
            return
        _press(_VK_TAB)
        _release(_VK_TAB)

    def _release(self):
        _release(_VK_TAB)       # 혹시 눌려있을 경우 대비
        _release(_VK_MENU)
        if self._shift_held:
            _release(_VK_SHIFT)
            self._shift_held = False
        self._alt_held = False
