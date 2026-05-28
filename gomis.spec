# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Gomis Motion Control
# 빌드: pyinstaller gomis.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # MediaPipe 손 인식 모델
        (str(ROOT / 'core' / 'hand_landmarker.task'), 'core'),
        # 설정 파일
        (str(ROOT / 'config' / 'settings.json'), 'config'),
        # Gomis 대시보드 HTML
        (str(ROOT / 'ui' / 'gomis.html'), 'ui'),
        (str(ROOT / 'ui' / 'dashboard.html'), 'ui'),
        # MediaPipe 내부 리소스 (모델/그래프 파일)
        (str(ROOT / 'venv' / 'Lib' / 'site-packages' / 'mediapipe'), 'mediapipe'),
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
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'sklearn',
        'PIL.ImageTk',   # tkinter 관련
        'tkinter',
        # torch CUDA 모듈 (CPU 전용 빌드)
        'torch.cuda',
        'torch.distributed',
        'torch.testing',
        'torchaudio',
        # torch._inductor — PyInstaller 격리 서브프로세스 크래시 원인, Whisper 미사용
        'torch._inductor',
        'torch._inductor.codegen',
        'torch._inductor.fx_passes',
        'torch._inductor.kernel',
        'torch._inductor.autoheuristic',
        'torch._inductor.lookup_table',
        'torch.ao',
        'torch.ao.quantization',
        'torch.ao.pruning',
        'torch.fx.experimental',
        'torch.onnx',
        'torch.quantization',
        'torch.profiler',
        'torch.utils.tensorboard',
        'tensorboard',
        # numba/llvmlite — 프로젝트 미사용, tbb12.dll 의존성 차단
        'numba',
        'llvmlite',
    ],
    noarchive=False,
    optimize=1,
)

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
    icon=None,          # 아이콘 파일 있으면 경로 지정
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
