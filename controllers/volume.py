import json
from pathlib import Path
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from core.gesture_engine import GESTURE_VOLUME_UP, GESTURE_VOLUME_DOWN

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"


class VolumeController:
    def __init__(self):
        devices = AudioUtilities.GetSpeakers()
        dev = getattr(devices, "_dev", devices)
        interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self._volume = cast(interface, POINTER(IAudioEndpointVolume))
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)["gesture"]
        self._default_step = cfg.get("volume_step", 3) / 100.0
        self._settings: dict | None = None

    def set_settings(self, settings: dict):
        self._settings = settings

    def handle(self, gesture: str):
        if gesture not in (GESTURE_VOLUME_UP, GESTURE_VOLUME_DOWN):
            return
        step = (self._settings["volume_step"] / 100.0) if self._settings else self._default_step
        current = self._volume.GetMasterVolumeLevelScalar()
        if gesture == GESTURE_VOLUME_UP:
            self._volume.SetMasterVolumeLevelScalar(min(1.0, current + step), None)
        else:
            self._volume.SetMasterVolumeLevelScalar(max(0.0, current - step), None)

    @property
    def level(self) -> float:
        return self._volume.GetMasterVolumeLevelScalar()
