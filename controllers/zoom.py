import ctypes
from core.gesture_engine import GESTURE_ZOOM_IN, GESTURE_ZOOM_OUT

# Windows SendInput 구조체 정의
_INPUT_KEYBOARD = 1
_INPUT_MOUSE    = 0
_KEYEVENTF_KEYUP      = 0x0002
_MOUSEEVENTF_WHEEL    = 0x0800
_VK_CONTROL           = 0x11
_WHEEL_DELTA          = 20


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_ushort),
        ("wScan",       ctypes.c_ushort),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT_UNION)]


def _ctrl_scroll(delta: int):
    """Ctrl+휠을 단일 SendInput 호출로 원자적 전송 — Chrome/Edge 호환."""
    inputs = (_INPUT * 3)(
        _INPUT(type=_INPUT_KEYBOARD,
               _input=_INPUT_UNION(ki=_KEYBDINPUT(wVk=_VK_CONTROL))),
        _INPUT(type=_INPUT_MOUSE,
               _input=_INPUT_UNION(mi=_MOUSEINPUT(mouseData=ctypes.c_ulong(delta),
                                                   dwFlags=_MOUSEEVENTF_WHEEL))),
        _INPUT(type=_INPUT_KEYBOARD,
               _input=_INPUT_UNION(ki=_KEYBDINPUT(wVk=_VK_CONTROL,
                                                   dwFlags=_KEYEVENTF_KEYUP))),
    )
    ctypes.windll.user32.SendInput(3, inputs, ctypes.sizeof(_INPUT))


class ZoomController:
    def handle(self, gesture: str):
        """Ctrl+휠(SendInput)로 줌 인/아웃 — 브라우저·탐색기·Office 범용."""
        if gesture == GESTURE_ZOOM_IN:
            _ctrl_scroll(_WHEEL_DELTA)
        elif gesture == GESTURE_ZOOM_OUT:
            _ctrl_scroll(-_WHEEL_DELTA)
