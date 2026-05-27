import sys
from pathlib import Path


def resource_path(*parts) -> Path:
    """PyInstaller 빌드(sys._MEIPASS) 또는 개발 환경 모두에서 리소스 경로 반환."""
    if hasattr(sys, '_MEIPASS'):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base.joinpath(*parts)
