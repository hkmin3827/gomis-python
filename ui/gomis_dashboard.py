from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from resource_path import resource_path
from ui.icon_helper import app_icon


class GomisDashboard(QMainWindow):
    """Gomis AI 대시보드 — QWebEngineView 기반 Canvas 애니메이션 창."""

    _state_signal  = pyqtSignal(str)           # 백그라운드 스레드 → Qt 메인 스레드
    _dialog_signal = pyqtSignal(str, str, str)  # (title, message, detail)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GOMIS")
        self.setWindowIcon(app_icon())
        self.resize(560, 660)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: #010108;")

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        html_path = str(resource_path('ui', 'gomis.html'))
        self._view.load(QUrl.fromLocalFile(html_path))

        # 신호 연결: 백그라운드 스레드 → Qt 메인 스레드
        self._state_signal.connect(self._apply_state)
        self._dialog_signal.connect(self._show_dialog)

    def set_state(self, state: str) -> None:
        """스레드 안전. 'idle' | 'speaking' | 'listening' | 'thinking'"""
        self._state_signal.emit(state)

    def show_error_dialog(self, title: str, message: str, detail: str = "") -> None:
        """백그라운드 스레드에서 안전하게 호출 가능."""
        self._dialog_signal.emit(title, message, detail)

    def _apply_state(self, state: str) -> None:
        self._view.page().runJavaScript(f"setGomisState('{state}');")

    def _show_dialog(self, title: str, message: str, detail: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        if detail:
            box.setDetailedText(detail)
        box.setIcon(QMessageBox.Warning)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
