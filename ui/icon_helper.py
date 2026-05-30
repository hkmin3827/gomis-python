import sys
import weakref
from pathlib import Path
from PyQt5.QtGui import QIcon

_cached: "QIcon | None" = None
_app_ref: "weakref.ref | None" = None


def app_icon() -> QIcon:
    """앱 아이콘(둥근 모서리 PNG) 반환. 캐싱하여 중복 로드 방지.

    QApplication 인스턴스가 교체되면 캐시를 자동 무효화한다.
    """
    global _cached, _app_ref
    from PyQt5.QtWidgets import QApplication
    current_app = QApplication.instance()
    cache_stale = (
        _cached is None
        or _cached.isNull()
        or _app_ref is None
        or _app_ref() is not current_app
    )
    if cache_stale:
        _app_ref = weakref.ref(current_app) if current_app else None
        if hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent.parent
        path = base / 'assets' / 'app-logo.png'
        if path.exists():
            _cached = QIcon(str(path))
        else:
            _cached = QApplication.style().standardIcon(65)
    return _cached  # type: ignore[return-value]
