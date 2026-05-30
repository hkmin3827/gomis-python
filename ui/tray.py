from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtCore import QObject, pyqtSignal
from ui.icon_helper import app_icon


class TrayIcon(QObject):
    quit_requested      = pyqtSignal()
    preview_toggled     = pyqtSignal()
    dashboard_toggled   = pyqtSignal()   # dashboard.html 창
    gomis_toggled       = pyqtSignal()   # gomis.html (Gomis AI) 창

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tray = QSystemTrayIcon(app_icon(), parent)
        self._tray.setToolTip("GOMIS")

        menu = QMenu()

        act_dashboard = QAction("대시보드 열기", menu)
        act_dashboard.triggered.connect(self.dashboard_toggled.emit)
        menu.addAction(act_dashboard)

        act_gomis = QAction("Gomis AI 창 열기", menu)
        act_gomis.triggered.connect(self.gomis_toggled.emit)
        menu.addAction(act_gomis)

        act_preview = QAction("모션인식 웹캠 창 열기", menu)
        act_preview.triggered.connect(self.preview_toggled.emit)
        menu.addAction(act_preview)

        menu.addSeparator()

        act_quit = QAction("종료", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.dashboard_toggled.emit()

    def notify(self, title: str, msg: str):
        self._tray.showMessage(title, msg, QSystemTrayIcon.Information, 2000)
