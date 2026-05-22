from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QObject, pyqtSignal
from pathlib import Path

ICON_PATH = Path(__file__).parent.parent / "config" / "icon.png"


class TrayIcon(QObject):
    quit_requested   = pyqtSignal()
    debug_toggled    = pyqtSignal(bool)
    preview_toggled  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debug_on = False

        # 아이콘 (없으면 기본 아이콘 사용)
        icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else QApplication.style().standardIcon(65)

        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip("Javis Motion Control")

        menu = QMenu()

        self._act_preview = QAction("미리보기 창 열기", menu)
        self._act_preview.triggered.connect(self.preview_toggled.emit)
        menu.addAction(self._act_preview)

        self._act_debug = QAction("디버그 모드: OFF", menu)
        self._act_debug.triggered.connect(self._toggle_debug)
        menu.addAction(self._act_debug)

        menu.addSeparator()

        act_quit = QAction("종료", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def _toggle_debug(self):
        self._debug_on = not self._debug_on
        self._act_debug.setText(f"디버그 모드: {'ON' if self._debug_on else 'OFF'}")
        self.debug_toggled.emit(self._debug_on)

    def _on_activated(self, reason):
        # 트레이 아이콘 더블클릭 → 미리보기 창 토글
        if reason == QSystemTrayIcon.DoubleClick:
            self.preview_toggled.emit()

    def notify(self, title: str, msg: str):
        self._tray.showMessage(title, msg, QSystemTrayIcon.Information, 2000)
