from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from core.gesture_engine import GESTURE_VOLUME_UP, GESTURE_VOLUME_DOWN

STEP = 0.03     # 한 번 발화 시 볼륨 변화량 (0.0~1.0 기준, 약 3%)


class VolumeController:
    def __init__(self):
        devices = AudioUtilities.GetSpeakers()
        # pycaw 최신 버전은 AudioDevice 래퍼를 반환하므로 _dev로 COM 객체에 접근
        dev = getattr(devices, "_dev", devices)
        interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self._volume = cast(interface, POINTER(IAudioEndpointVolume))

    def handle(self, gesture: str):
        if gesture not in (GESTURE_VOLUME_UP, GESTURE_VOLUME_DOWN):
            return
        current = self._volume.GetMasterVolumeLevelScalar()
        if gesture == GESTURE_VOLUME_UP:
            self._volume.SetMasterVolumeLevelScalar(min(1.0, current + STEP), None)
        else:
            self._volume.SetMasterVolumeLevelScalar(max(0.0, current - STEP), None)

    @property
    def level(self) -> float:
        """현재 볼륨 (0.0~1.0)."""
        return self._volume.GetMasterVolumeLevelScalar()
