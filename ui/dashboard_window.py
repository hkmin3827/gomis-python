from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, pyqtSignal
from resource_path import resource_path


class DashboardWindow(QMainWindow):
    closed = pyqtSignal()  # 창 닫힐 때 트레이 show 신호

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gomis — Motion Control Dashboard")
        self.resize(1280, 860)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        html_path = str(resource_path('ui', 'dashboard.html'))
        self._view.load(QUrl.fromLocalFile(html_path))

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.closed.emit()
