import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap


class PreviewWindow(QWidget):
    def __init__(self, engine_runner):
        """
        engine_runner: 매 프레임 (frame_bgr, gesture, state, handedness) 를 반환하는 callable.
        """
        super().__init__()
        self._runner = engine_runner
        self._debug  = False

        self.setWindowTitle("Javis Motion Control")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(640, 520)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background: black;")

        self._info = QLabel("손을 카메라 앞에 올려주세요", self)
        self._info.setAlignment(Qt.AlignCenter)
        self._info.setStyleSheet("color: white; background: #1e1e1e; font-size: 14px; padding: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label)
        layout.addWidget(self._info)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_debug(self, enabled: bool):
        self._debug = enabled

    def _tick(self):
        result = self._runner()
        if result is None:
            return

        frame, gesture, state, handedness = result

        if self._debug and frame is not None:
            self._draw_debug(frame, gesture, state, handedness)

        if frame is not None:
            self._label.setPixmap(self._to_pixmap(frame))

        side = f"[{handedness}] " if handedness else ""
        self._info.setText(f"{side}{gesture}  |  state: {state}" if gesture != "none" else "대기 중")

    def _draw_debug(self, frame, gesture, state, handedness):
        h, w = frame.shape[:2]
        cv2.putText(frame, f"{handedness or ''} {gesture}", (10, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.putText(frame, f"state: {state}", (10, 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)

    @staticmethod
    def _to_pixmap(frame_bgr) -> QPixmap:
        rgb   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img   = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        return QPixmap.fromImage(img).scaled(640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def closeEvent(self, event):
        event.ignore()
        self.hide()