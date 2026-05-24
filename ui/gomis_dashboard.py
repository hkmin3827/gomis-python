import os
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, Qt, pyqtSignal


class GomisDashboard(QMainWindow):
    """Gomis AI 대시보드 — QWebEngineView 기반 Canvas 애니메이션 창."""

    _state_signal = pyqtSignal(str)  # 백그라운드 스레드에서 set_state() 호출 시 Qt 스레드로 전달

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gomis")
        self.resize(560, 660)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: #010108;")

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        html_path = os.path.join(os.path.dirname(__file__), 'gomis.html')
        self._view.load(QUrl.fromLocalFile(html_path))

        # 신호 연결: 백그라운드 스레드 → Qt 메인 스레드
        self._state_signal.connect(self._apply_state)

    def set_state(self, state: str) -> None:
        """스레드 안전. 'idle' | 'speaking' | 'listening' | 'thinking'"""
        self._state_signal.emit(state)

    def _apply_state(self, state: str) -> None:
        self._view.page().runJavaScript(f"setGomisState('{state}');")

    def closeEvent(self, event):
        event.ignore()
        self.hide()
