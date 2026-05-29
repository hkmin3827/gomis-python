import os
import sys
import json
import signal
import threading
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """요청마다 별도 스레드 처리 — 한 요청이 느려도 다음 요청 차단하지 않음."""
    daemon_threads = True

# MediaPipe 내부 Google 원격 측정 에러 로그 억제 (1회)
os.environ.setdefault("GLOG_minloglevel", "3")


# PyInstaller 빌드 시 torch/lib 디렉토리를 DLL 검색 경로에 먼저 등록해야
# c10.dll WinError 1114 (DLL 초기화 실패) 방지됨.
# Qt가 DLL 검색 경로를 변경하기 전에 반드시 실행.
if getattr(sys, 'frozen', False):
    _torch_lib = os.path.join(getattr(sys, '_MEIPASS', ''), 'torch', 'lib')
    if os.path.isdir(_torch_lib):
        _torch_dll_dir = os.add_dll_directory(_torch_lib)  # noqa: F841 — GC되면 등록 해제되므로 반환값 유지 필수
        os.environ['PATH'] = _torch_lib + os.pathsep + os.environ.get('PATH', '')
try:
    import torch  # noqa: F401  # type: ignore[import]
except Exception:
    pass

CONFIG_PATH = Path(__file__).parent / "config" / "settings.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _make_handler(config_path: Path, app_state: dict, live_settings: dict):
    """dashboard.html ↔ Python 브리지 HTTP 핸들러 팩토리."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass  # 콘솔 로그 억제

        def _respond(self, code: int, body: str = ""):
            data = body.encode()
            # file:// 로컬 페이지만 허용 (QtWebEngine은 Origin: file:// 전송)
            origin = self.headers.get("Origin", "")
            allowed = origin if (origin == "null" or origin.startswith("file://")) else ""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            if allowed:
                self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):  # CORS preflight
            self._respond(204)

        def do_GET(self):
            if self.path == "/get-settings":
                self._respond(200, json.dumps(live_settings))
            else:
                self._respond(404, '{"error":"not found"}')

        def do_POST(self):
            length = min(int(self.headers.get("Content-Length", 0)), 4096)
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {}

            if self.path == "/start":
                app_state["running"] = True
                app_state["show_gomis"] = True   # Qt 메인 스레드에서 감지 후 표시
                self._respond(200, '{"ok":true}')

            elif self.path == "/stop":
                app_state["running"] = False
                app_state["hide_gomis"] = True   # Qt 메인 스레드에서 감지 후 숨김
                self._respond(200, '{"ok":true}')

            elif self.path == "/set-name":
                name = str(payload.get("name", "")).strip()
                try:
                    cfg = json.loads(config_path.read_text(encoding="utf-8"))
                    cfg["user_name"] = name
                    config_path.write_text(
                        json.dumps(cfg, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    app_state["user_name"] = name
                    self._respond(200, '{"ok":true}')
                except Exception as e:
                    self._respond(500, f'{{"error":"{e}"}}')

            elif self.path == "/save-settings":
                int_keys   = ("scroll_speed", "zoom_delta", "cursor_speed")
                float_keys = ("volume_step",)
                for k in int_keys:
                    if k in payload:
                        live_settings[k] = int(payload[k])
                for k in float_keys:
                    if k in payload:
                        live_settings[k] = float(payload[k])
                if "auto_enter" in payload:
                    live_settings["auto_enter"] = bool(payload["auto_enter"])
                try:
                    cfg = json.loads(config_path.read_text(encoding="utf-8"))
                    cfg["gesture"]["cursor_speed"] = live_settings["cursor_speed"]
                    cfg["gesture"]["scroll_speed"] = live_settings["scroll_speed"]
                    cfg["gesture"]["volume_step"]  = live_settings["volume_step"]
                    cfg["gesture"]["zoom_delta"]   = live_settings["zoom_delta"]
                    if "voice" not in cfg:
                        cfg["voice"] = {}
                    cfg["voice"]["auto_enter"] = live_settings["auto_enter"]
                    config_path.write_text(
                        json.dumps(cfg, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    self._respond(200, '{"ok":true}')
                except Exception as e:
                    self._respond(500, f'{{"error":"{e}"}}')
            else:
                self._respond(404, '{"error":"not found"}')

    return Handler


def _start_server(config_path: Path, app_state: dict, live_settings: dict, port: int = 7777):
    handler = _make_handler(config_path, app_state, live_settings)
    server  = _ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def main():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    import PyQt5.QtWebEngineWidgets  # noqa: F401 — QApplication 전에 임포트 필수
    # QWebEngineView 다중 창 WebGL 공유 — QApplication 생성 전 필수
    QApplication.setAttribute(Qt.ApplicationAttribute(4))  # AA_ShareOpenGLContexts
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 창 닫아도 트레이에 유지
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config    = load_config()
    features  = config["features"]

    # 런타임 공유 상태 (서버 ↔ 메인 루프)
    # running=False: 대시보드 START 버튼을 눌러야 제스처 인식 활성화
    app_state = {
        "running":    False,
        "user_name":  config.get("user_name", "").strip(),
        "show_gomis": False,
        "hide_gomis": False,
    }

    # 감도 설정 — 대시보드 세팅 패널에서 실시간 변경 가능
    gesture_cfg = config.get("gesture", {})
    voice_cfg   = config.get("voice", {})
    live_settings = {
        "cursor_speed": gesture_cfg.get("cursor_speed", 30),
        "scroll_speed": gesture_cfg.get("scroll_speed", 40),
        "volume_step":  gesture_cfg.get("volume_step", 3),
        "zoom_delta":   gesture_cfg.get("zoom_delta", 20),
        "auto_enter":   voice_cfg.get("auto_enter", True),
    }

    _start_server(CONFIG_PATH, app_state, live_settings)

    from core import Camera, HandTracker
    from core.gesture_engine import (
        GestureEngine,
        GESTURE_CURSOR, GESTURE_CLICK, GESTURE_DOUBLE_CLICK,
        GESTURE_VOICE_START, GESTURE_VOICE_END,
        GESTURE_CLAUDE_START, GESTURE_CLAUDE_END,
        GESTURE_LOCK_TOGGLE,
    )
    from controllers import (
        CursorController, ScrollController,
        VolumeController, WindowSwitcher, ZoomController,
    )

    from voice.whisper_stt import VoiceTyper
    from voice.claude_client import ask_claude, NOT_INSTALLED, NOT_AUTHENTICATED, TOKEN_EXHAUSTED
    from voice.tts import speak_async

    cam     = Camera()
    tracker = HandTracker()
    engine  = GestureEngine(tracker)

    cursor      = CursorController()
    scroll      = ScrollController()
    volume      = VolumeController()
    windows     = WindowSwitcher()
    zoom        = ZoomController()

    whisper_cfg = config.get("whisper", {})
    voice_typer = VoiceTyper(
        model_name=whisper_cfg.get("model", "small"),
        language=whisper_cfg.get("language", "ko"),
    )

    # 컨트롤러에 live_settings 주입 (딕셔너리 참조 공유 → 즉시 반영)
    cursor.set_settings(live_settings)
    scroll.set_settings(live_settings)
    volume.set_settings(live_settings)
    zoom.set_settings(live_settings)

    voice_state  = {"status": "idle"}   # "idle" | "recording" | "transcribing"
    claude_state = {"status": "idle"}   # "idle" | "recording" | "thinking"
    lock_state   = {"locked": False}

    cam.open()

    # ── 백그라운드 캡처/추론 스레드 ──────────────────────────────────
    # cam.read() + MediaPipe 추론을 Qt 타이머와 분리.
    # Qt 타이머는 항상 최신 결과만 읽어 일정한 33ms 간격 유지 → 커서 끊김 제거.
    _cap_state = {"frame": None, "hands": []}
    _cap_lock  = threading.Lock()

    def _bg_capture():
        while True:
            ok, fr = cam.read()
            if not ok:
                time.sleep(0.01)
                continue
            # running=False 일 때 MediaPipe(CPU 집약) 건너뜀 — 대기 중 자원 절약
            hs = tracker.process_all(fr) if app_state["running"] else []
            with _cap_lock:
                _cap_state["frame"] = fr
                _cap_state["hands"] = hs

    threading.Thread(target=_bg_capture, daemon=True).start()

    # PreviewWindow 의 타이머가 호출
    def run_frame():
        with _cap_lock:
            frame = _cap_state["frame"]
            hands = list(_cap_state["hands"])
        if frame is None:
            return None

        # 대시보드 STOP 상태: 카메라 영상만 보여주고 제스처 처리 건너뜀
        if not app_state["running"]:
            return frame, "[대기 중 — 대시보드 START 버튼으로 시작]", None, None

        both_hands = len(hands) >= 2
        hand       = hands[0] if hands else None

        gesture = engine.detect(None if both_hands else hand)

        for h in hands:
            tracker.draw(frame, h.landmarks)

        # ── 잠금 토글 감지 (잠금 중에도 항상 체크) ───────────────────
        lock_trigger = engine.detect_lock(hands)
        if lock_trigger == GESTURE_LOCK_TOGGLE:
            lock_state["locked"] = not lock_state["locked"]
            if lock_state["locked"]:
                gomis_dash.set_state("locked")
                tray.notify("Gomis 🔒", "잠금 모드 ON — 양손 엄지 Up 1.5초로 해제")
            else:
                gomis_dash.set_state("idle")
                tray.notify("Gomis 🔓", "잠금 모드 OFF")

        # ── 잠금 상태이면 이하 모든 제스처 처리 건너뜀 ──────────────
        if lock_state["locked"]:
            return frame, "[🔒 잠금 모드]", engine.state, hand.handedness if hand else None

        # ── 박수: 음성 타이핑 ──────────────────────────────────────────
        clap = engine.detect_clap(hands)
        if clap == GESTURE_VOICE_START and voice_state["status"] == "idle" \
                and claude_state["status"] == "idle":
            voice_state["status"] = "recording"

            def _on_voice_auto_stop():
                if voice_state["status"] == "recording":
                    voice_state["status"] = "idle"

            voice_typer.start(on_auto_stop=_on_voice_auto_stop)
            tray.notify("Gomis 🎤", "녹음 중… 다시 박수치면 종료")

        elif clap == GESTURE_VOICE_END and voice_state["status"] == "recording":
            voice_state["status"] = "transcribing"
            tray.notify("Gomis", "음성 인식 중…")

            def _do_transcribe():
                try:
                    text = voice_typer.stop_and_transcribe(auto_enter=live_settings["auto_enter"])
                    if text:
                        tray.notify(" ✅", f"입력: {text[:40]}")
                    else:
                        tray.notify("Gomis", "인식된 텍스트 없음")
                except Exception as e:
                    tray.notify("Gomis ❌", f"음성 인식 오류: {e}")
                finally:
                    voice_state["status"] = "idle"

            threading.Thread(target=_do_transcribe, daemon=True).start()

        # ── 손가락 모으기: Claude 대화 ────────────────────────────────
        claude_trigger = engine.detect_claude_trigger(hands)
        if claude_trigger == GESTURE_CLAUDE_START and claude_state["status"] == "idle" \
                and voice_state["status"] == "idle":
            # 인사말 TTS → 완료 후 녹음 시작 (Claude 호출 없음)
            claude_state["status"] = "greeting"
            gomis_dash.set_state("speaking")
            tray.notify("Gomis 🤖", "Gomis 인사 중…")

            def _start_recording():
                # TTS 종료 직후 오디오 드라이버 전환 딜레이 — input overflow 방지
                time.sleep(0.4)
                claude_state["status"] = "recording"
                gomis_dash.set_state("listening")
                voice_typer.start(max_sec=60)
                tray.notify("Gomis 🎤", "녹음 중… 다시 손 모으면 전송")

            _name    = app_state["user_name"]
            greeting = f"네 {_name}님 무엇을 도와드릴까요?" if _name else "네 무엇을 도와드릴까요?"
            speak_async(greeting, on_done=_start_recording)

        elif claude_trigger == GESTURE_CLAUDE_END and claude_state["status"] == "recording":
            claude_state["status"] = "thinking"
            gomis_dash.set_state("thinking")
            tray.notify("Gomis", "Claude 생각 중…")

            def _do_claude():
                try:
                    text = voice_typer.stop_and_transcribe(auto_enter=False, do_type=False)
                    if not text:
                        tray.notify("Gomis", "인식된 텍스트 없음")
                        claude_state["status"] = "idle"
                        gomis_dash.set_state("idle")
                        return
                    tray.notify("Gomis 🤖", f"질문: {text[:40]}")
                    result = ask_claude(text)

                    if not result.ok:
                        # ── 에러 타입별 처리 ────────────────────────────
                        if result.error_type == NOT_INSTALLED:
                            tray.notify("Gomis ❌", "Claude CLI 미설치 — 설치 안내를 확인하세요")
                            gomis_dash.show_error_dialog(
                                "Claude CLI 설치 필요",
                                "Claude CLI가 설치되어 있지 않습니다.",
                                result.detail,
                            )
                        elif result.error_type == NOT_AUTHENTICATED:
                            tray.notify("Gomis ⚠️", "Claude 회원 연결이 필요합니다")
                            gomis_dash.show_error_dialog(
                                "Claude 로그인 필요",
                                "Claude CLI에 로그인되어 있지 않습니다.\n"
                                "아래 안내에 따라 로그인 후 재시작해 주세요.",
                                result.detail,
                            )
                        elif result.error_type == TOKEN_EXHAUSTED:
                            tray.notify("Gomis ⚠️", result.text[:60])
                        else:  # UNKNOWN_ERROR
                            tray.notify("Gomis ❌", result.text[:60])
                            if result.detail:
                                gomis_dash.show_error_dialog(
                                    "Claude 오류",
                                    result.text,
                                    result.detail,
                                )
                        speak_async(result.text)
                        claude_state["status"] = "idle"
                        gomis_dash.set_state("idle")
                        return

                    if result.text:
                        tray.notify("Gomis 💬", f"{result.text[:60]}")
                        gomis_dash.set_state("speaking")

                        def _after_response():
                            claude_state["status"] = "idle"
                            gomis_dash.set_state("idle")

                        speak_async(result.text, on_done=_after_response)
                    else:
                        tray.notify("Gomis", "Claude 응답 없음")
                        claude_state["status"] = "idle"
                        gomis_dash.set_state("idle")
                except Exception as e:
                    tray.notify("Gomis ❌", f"Claude 오류: {e}")
                    claude_state["status"] = "idle"
                    gomis_dash.set_state("idle")

            threading.Thread(target=_do_claude, daemon=True).start()

        # ── 단일 손 제스처 — 양손이면 발화 차단 ─────────────────────
        if not both_hands:
            if features.get("cursor") and gesture == GESTURE_CURSOR and hand:
                cursor.move(hand.landmarks)

            if features.get("click"):
                if gesture == GESTURE_CLICK:
                    cursor.click()
                elif gesture == GESTURE_DOUBLE_CLICK:
                    cursor.double_click()

            if features.get("scroll"):
                scroll.handle(gesture)

            if features.get("volume"):
                volume.handle(gesture)

            if features.get("window_switch"):
                windows.handle(gesture)

            zoom.handle(gesture)

        handedness = hand.handedness if hand else None
        if claude_state["status"] != "idle":
            disp_gesture = f"[{len(hands)}H] 🤖 {claude_state['status']}"
        elif voice_state["status"] != "idle":
            disp_gesture = f"[{len(hands)}H] 🎤 {voice_state['status']}"
        else:
            disp_gesture = f"[{len(hands)}H] {gesture}"
        return frame, disp_gesture, engine.state, handedness

    from PyQt5.QtCore import QTimer
    from ui import PreviewWindow, TrayIcon, GomisDashboard, DashboardWindow

    preview        = PreviewWindow(run_frame)
    tray           = TrayIcon()
    gomis_dash     = GomisDashboard()
    main_dashboard = DashboardWindow()

    tray.quit_requested.connect(lambda: _shutdown(app, cam, tracker, windows, voice_typer))
    tray.preview_toggled.connect(lambda: preview.show() if preview.isHidden() else preview.hide())

    def _open_dashboard():
        main_dashboard.show()
        main_dashboard.raise_()

    tray.dashboard_toggled.connect(_open_dashboard)
    tray.gomis_toggled.connect(lambda: gomis_dash.show() if gomis_dash.isHidden() else gomis_dash.raise_())

    # HTTP 서버(별도 스레드) → Qt 메인 스레드: show_gomis / hide_gomis 플래그 폴링
    def _poll_app_state():
        if app_state.get("show_gomis"):
            app_state["show_gomis"] = False
            gomis_dash.show()
            gomis_dash.raise_()
        if app_state.get("hide_gomis"):
            app_state["hide_gomis"] = False
            gomis_dash.hide()

    _state_timer = QTimer()
    _state_timer.timeout.connect(_poll_app_state)
    _state_timer.start(200)  # 200ms 간격 폴링

    # 앱 시작: 대시보드만 오픈, Gomis AI 창은 START 버튼 시 표시
    main_dashboard.show()
    tray.show()
    tray.notify("Gomis 시작", "대시보드 START 버튼으로 모션 인식을 시작하세요.")

    sys.exit(app.exec_())


def _shutdown(app, cam, tracker, windows=None, voice_typer=None):
    if windows:
        windows.force_release()
    if voice_typer:
        voice_typer.close()
    cam.close()
    tracker.close()
    app.quit()


if __name__ == "__main__":
    main()
