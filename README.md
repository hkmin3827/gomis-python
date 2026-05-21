# Javis Motion Control

손 제스처만으로 Windows 데스크톱을 제어하는 로컬 실행 앱.  
키보드·마우스 없이 웹캠 앞에서 손을 움직이면 커서 이동, 클릭, 스크롤, 볼륨 조절, 창 전환이 가능합니다.

---

## 동작 원리

```
웹캠 → OpenCV(프레임) → MediaPipe(21개 손 좌표) → GestureEngine(제스처 판별) → PyAutoGUI/pycaw(OS 제어)
```

- **완전 로컬 실행** — 인터넷 연결 불필요, 원격 서버 없음
- **OS 접근 수준** — 일반 사용자 권한만 사용. 커서·클릭은 PyAutoGUI가 Windows `SendInput()` API를 통해 가상 이벤트로 전송 (드라이버·커널 접근 없음)
- **음성 인식(2단계)** — Whisper 로컬 모델, 외부 전송 없음

---

## 기술 스택

| 역할 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| 카메라 캡처 | OpenCV (`cv2.VideoCapture`) |
| 손 랜드마크 감지 | MediaPipe Hands (Tasks API) |
| 커서·클릭 제어 | PyAutoGUI |
| 볼륨 제어 | pycaw (Windows COM API) |
| 창 전환 | pywin32 (Win32 API) |
| UI | PyQt5 + pystray |
| 음성 인식 (2단계) | OpenAI Whisper (로컬) |
| Claude 연동 (2단계) | Anthropic Python SDK |

---

## 기능 요구사항 (명세)

### 1단계 — 핵심 제어
| 기능 | 설명 |
|------|------|
| 커서 이동 | 검지만 편 상태에서 손 위치로 커서 이동 |
| 클릭 | 손가락 오므리기 (끝이 손바닥 중심으로 모임) |
| 더블클릭 | 오므리기 동작을 0.4초 이내 2회 반복 |
| 스크롤 업 | 검지+중지 V자 → 위로 드래그 |
| 스크롤 다운 | 검지+중지 V자 → 아래로 드래그 |
| 줌 인 | 엄지+검지 꼬집은 상태에서 V자로 벌리기 |
| 줌 아웃 | 엄지+검지 V자 상태에서 꼬집기 |
| 볼륨 업 | **오른손** 샤카(엄지+새끼) → 연속 상승 (최대 3/초) |
| 볼륨 다운 | **왼손** 샤카(엄지+새끼) → 연속 하강 (최대 3/초) |
| 창 전환(오른쪽) | **오른손** 가로 방향 + 손가락 모음 포즈 |
| 창 전환(왼쪽) | **왼손** 가로 방향 + 손가락 모음 포즈 |
| 제스처 종료 | 손바닥 펴기 → 연속 제스처(스크롤·줌·볼륨) 종료 |

### 2단계 — Claude 연동
- 특정 제스처 → Whisper 음성 인식 → Claude API 호출 → 응답 표시

### 3단계 — 부가 기능
- 밝기 조절, 미디어 재생/일시정지, 스크린샷, 잠금 모드, 제스처 커스터마이징 UI, 디버그 모드

---

## 손동작 레퍼런스

| 제스처 | 손 모양 | 방식 |
|--------|---------|------|
| 커서 이동 | 검지만 펴기 | 정적 — 손 위치 추적 |
| 클릭 | 손가락 오므리기 | 원샷 |
| 더블클릭 | 오므리기 × 2 (0.4초 이내) | 원샷 × 2 |
| 스크롤 | 검지+중지 V자 (드래그) | 연속 — 손바닥 펴서 종료 |
| 줌 인/아웃 | 엄지+검지 꼬집기→벌리기 | 연속 — 손바닥 펴서 종료 |
| 볼륨 조절 | 샤카 (엄지+새끼), 좌/우손 구분 | 연속 — 손바닥 펴서 종료 |
| 창 전환 | 손 가로 방향 + 손가락 모음, 좌/우손 구분 | 원샷 |
| 리셋(종료) | 손바닥 펴기 | 연속 제스처만 해당 |

> 레퍼런스 이미지: `docs/motion-capture-img/`

---

## 프로젝트 구조

```
javis-prj/
├── main.py                    # 앱 엔트리포인트
├── core/
│   ├── camera.py              # OpenCV 카메라 캡처
│   ├── hand_tracker.py        # MediaPipe 손 랜드마크 추출
│   ├── gesture_engine.py      # 상태 기계 기반 제스처 판별
│   └── hand_landmarker.task   # MediaPipe 모델 파일 (자동 다운로드)
├── controllers/
│   ├── cursor.py              # 커서 이동·클릭
│   ├── scroll.py              # 스크롤
│   ├── volume.py              # 볼륨 조절
│   └── window_switcher.py     # 창 전환
├── voice/
│   ├── whisper_stt.py         # Whisper 음성 인식
│   └── claude_client.py       # Anthropic SDK 연동
├── ui/
│   ├── preview_window.py      # PyQt5 카메라 미리보기 창
│   ├── tray.py                # 시스템 트레이 아이콘
│   └── debug_overlay.py       # 디버그 오버레이 (랜드마크·제스처·FPS)
├── config/
│   └── settings.json          # 카메라·제스처 감도·기능 ON/OFF
├── docs/
│   └── motion-capture-img/    # 손동작 레퍼런스 이미지
├── tasks/
│   ├── todo.md                # 개발 체크리스트
│   └── progress.md            # 작업 기록
├── .env                       # API 키 (공유 금지)
├── .env.example               # 환경변수 예시
├── requirements.txt
└── test_camera.py             # 웹캠 + 랜드마크 확인용 테스트
```

---

## 시스템 동작 방식

```
┌─────────────────────────────────────────────────────┐
│                    main.py (앱 시작)                  │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   Camera (OpenCV)          │  ← 30fps 프레임 캡처
         └─────────────┬─────────────┘
                       │ BGR 프레임
         ┌─────────────▼─────────────┐
         │   HandTracker (MediaPipe)  │  ← 21개 랜드마크 + 손 방향(Left/Right)
         └─────────────┬─────────────┘
                       │ HandResult
         ┌─────────────▼─────────────┐
         │   GestureEngine (상태기계) │  ← 제스처 이름 반환
         │   IDLE / CURSOR / DRAG /   │
         │   ZOOM / VOLUME            │
         └─────────────┬─────────────┘
                       │ gesture name
         ┌─────────────▼─────────────┐
         │      Controllers           │
         │  cursor / scroll /         │  ← PyAutoGUI, pycaw, pywin32
         │  volume / window_switch    │
         └───────────────────────────┘
```

**제스처 상태 전이:**
```
[IDLE] ──검지만 펴기──────→ [CURSOR]  손바닥 펴기로 종료
       ──V자──────────────→ [DRAG]    손바닥 펴기로 종료
       ──꼬집기────────────→ [ZOOM]    손바닥 펴기로 종료
       ──샤카──────────────→ [VOLUME]  손바닥 펴기로 종료
       ──오므리기 (원샷)───→ CLICK / DOUBLE_CLICK (상태 없음)
       ──가로 손 (원샷)────→ WINDOW_SWITCH (상태 없음)
```

---

## 설치 및 실행

```powershell
# 1. 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 환경변수 설정
copy .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력

# 4. 실행
python main.py

# 웹캠 + 랜드마크 테스트
python test_camera.py
```

> **주의:** 실행 전 반드시 가상환경(`venv`) 활성화 확인
