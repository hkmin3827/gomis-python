import sys
from pathlib import Path
from PyQt5.QtGui import QIcon

_cached: "QIcon | None" = None


def app_icon() -> QIcon:
    """앱 아이콘(둥근 모서리 PNG) 반환. 캐싱하여 중복 로드 방지."""
    global _cached
    if _cached is None or _cached.isNull():
        if hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent.parent
        path = base / 'assets' / 'app-logo.png'
        if path.exists():
            _cached = QIcon(str(path))
        else:
            from PyQt5.QtWidgets import QApplication
            _cached = QApplication.style().standardIcon(65)
    return _cached
