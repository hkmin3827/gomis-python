import sys

from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, pyqtSignal
from resource_path import resource_path


class DashboardWindow(QMainWindow):
    closed = pyqtSignal()  # 창 닫힐 때 트레이 show 신호

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gomis — Motion Control Dashboard")

        # 화면 크기의 70% 비율로 창 크기 결정 — 해상도 무관하게 일정 비율 유지
        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.70)
        h = int(screen.height() * 0.78)
        self.resize(w, h)

        self._dev_mode = not getattr(sys, "frozen", False)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        if self._dev_mode:
            self._view.loadFinished.connect(self._inject_dev_onboarding)

        html_path = str(resource_path('ui', 'dashboard.html'))
        self._view.load(QUrl.fromLocalFile(html_path))

    def _inject_dev_onboarding(self, ok: bool) -> None:
        """개발 모드 전용: 매 실행마다 온보딩 화면을 보여주되, UI 애니메이션만 실행 (settings.json 저장 안 함)."""
        if not ok:
            return
        js = """
        (function() {
            localStorage.removeItem('gomis_user');
            var modal = document.getElementById('onboarding');
            if (modal) {
                modal.style.display = 'flex';
                modal.style.opacity = '1';
            }
        })();
        """
        self._view.page().runJavaScript(js)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.closed.emit()
