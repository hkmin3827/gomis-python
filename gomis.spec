# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Gomis Motion Control
# 빌드: pyinstaller gomis.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[
        # ctranslate2 런타임에서 동적 로드 — PyInstaller 자동 감지 안 됨
        (str(ROOT / 'venv' / 'Lib' / 'site-packages' / 'ctranslate2' / 'cudnn64_9.dll'), 'ctranslate2'),
    ],
    datas=[
        # 앱 로고 (아이콘)
        (str(ROOT / 'assets' / 'app-logo.png'), 'assets'),
        # MediaPipe 손 인식 모델
        (str(ROOT / 'core' / 'hand_landmarker.task'), 'core'),
        # 설정 파일
        (str(ROOT / 'config' / 'settings.json'), 'config'),
        # Gomis 대시보드 HTML
        (str(ROOT / 'ui' / 'gomis.html'), 'ui'),
        (str(ROOT / 'ui' / 'dashboard.html'), 'ui'),
        # MediaPipe 내부 리소스 (모델/그래프 파일)
        (str(ROOT / 'venv' / 'Lib' / 'site-packages' / 'mediapipe'), 'mediapipe'),
        # faster-whisper small 모델 (HuggingFace 캐시에서 번들에 내장)
        # 첫 실행 다운로드 불필요, 오프라인 동작, 심링크 경고 없음
        (r'C:\Users\hkmin\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120', 'whisper_model'),
        # faster-whisper Silero VAD 모델 (vad_filter=True 시 런타임 로드 — PyInstaller 자동 수집 안 됨)
        # ※ onnx 파일만 복사 — assets 디렉터리 통째 복사 시 __init__.py가 PYZ의 faster_whisper 패키지를 섀도잉할 수 있음
        (str(ROOT / 'venv' / 'Lib' / 'site-packages' / 'faster_whisper' / 'assets' / 'silero_vad_v6.onnx'), 'faster_whisper/assets'),
    ],
    hiddenimports=[
        # PyQt5 WebEngine
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebEngine',
        'PyQt5.QtNetwork',
        # MediaPipe (0.10+ 구조: mediapipe.python 패키지 없음, tasks만 존재)
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.vision',
        # pycaw
        'pycaw',
        'pycaw.pycaw',
        # pynput (백그라운드 키보드 훅)
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        # sounddevice
        'sounddevice',
        # comtypes
        'comtypes.stream',
        # edge-tts
        'edge_tts',
        # pystray
        'pystray._win32',
        # whisper
        'whisper',
        'whisper.audio',
        'whisper.model',
        'whisper.transcribe',
        'whisper.tokenizer',
        # matplotlib (mediapipe 내부 의존성)
        'matplotlib',
        'matplotlib.pyplot',
    ],
    excludes=[
        # 사용하지 않는 대형 패키지
        # ※ scipy는 noisereduce(scipy.signal)가 요구하므로 제외하면 안 됨 — transcribe 단계 크래시 원인
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'sklearn',
        'PIL.ImageTk',   # tkinter 관련
        'tkinter',
        # torch 미사용 서브모듈만 선별 제외 (CPU 전용 빌드)
        # ※ import torch가 실제 로드하는 서브모듈(cuda·distributed·testing·ao·
        #    fx.experimental·quantization·profiler)은 제외하면 `import torch` 자체가
        #    ModuleNotFoundError로 깨진다 → 절대 제외 금지. 아래는 import torch가
        #    로드하지 않음을 확인한 항목만 제외한다.
        'torchaudio',                       # 별도 패키지, 미사용
        # torch._inductor — PyInstaller 격리 서브프로세스 크래시 원인, import torch 미로드
        'torch._inductor',
        'torch._inductor.codegen',
        'torch._inductor.fx_passes',
        'torch._inductor.kernel',
        'torch._inductor.autoheuristic',
        'torch._inductor.lookup_table',
        'torch.onnx',                       # import torch 미로드 (faster-whisper는 onnxruntime 사용)
        'torch.utils.tensorboard',
        'tensorboard',
        # numba/llvmlite — 프로젝트 미사용, tbb12.dll 의존성 차단
        'numba',
        'llvmlite',
    ],
    noarchive=False,
    optimize=1,
)

# ── PyQt5가 번들하는 구버전 VC 런타임(14.26)을 시스템 최신 버전으로 교체 ──
# ctranslate2.dll은 최신 MSVCP140 심볼을 요구하는데, Qt가 시작 시 먼저 로드한
# 구버전 MSVCP140.dll(Qt5/bin, 14.26)이 프로세스에 상주해 ctranslate2 모델 로드
# 시점에 액세스 위반(0xC0000005)으로 크래시한다. 번들 내 모든 VC 런타임 복사본을
# 시스템 System32의 최신 버전(14.44)으로 통일해 근본 해결한다.
import os as _os
_VC_RUNTIME = {
    'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll',
    'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll',
}
_SYS32 = _os.path.join(_os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
_fixed_binaries = []
for _entry in a.binaries:
    _dest, _src, _typ = _entry
    if _os.path.basename(_dest).lower() in _VC_RUNTIME:
        _sysdll = _os.path.join(_SYS32, _os.path.basename(_dest))
        if _os.path.isfile(_sysdll):
            _entry = (_dest, _sysdll, _typ)  # 소스를 시스템 최신 DLL로 교체
    _fixed_binaries.append(_entry)
a.binaries = _fixed_binaries

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Gomis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 압축 시 Qt 오류 발생 가능 — 비활성
    console=False,      # 콘솔 창 숨김
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'app-logo.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Gomis',
)
