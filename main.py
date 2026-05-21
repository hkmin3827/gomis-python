"""
Javis Motion Control — 엔트리포인트
손 제스처로 데스크톱을 제어하는 로컬 앱
"""

import sys
import json
import signal
from pathlib import Path
from dotenv import load_dotenv

# .env 로드 (ANTHROPIC_API_KEY 등)
load_dotenv()

CONFIG_PATH = Path(__file__).parent / "config" / "settings.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("=== Javis Motion Control 시작 ===")

    config = load_config()
    print(f"설정 로드 완료: 카메라 인덱스={config['camera']['index']}")

    # PyQt5 앱 초기화
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("Javis Motion Control")

    # Ctrl+C 로 종료 가능하도록
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # 미리보기 창 실행 (추후 ui/preview_window.py 에서 import)
    print("UI 모듈 준비 중... (다음 단계에서 구현)")

    # 이벤트 루프 시작
    print("앱 실행 중. 종료하려면 Ctrl+C 또는 트레이 아이콘 → 종료.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
