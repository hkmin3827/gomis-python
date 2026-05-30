"""
Claude Code CLI subprocess 호출 모듈.
`claude -p "prompt"` 로 응답 텍스트를 반환한다.
"""
import logging
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("voice")

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# 에러 타입 상수
NOT_INSTALLED     = "not_installed"
NOT_AUTHENTICATED = "not_authenticated"
TOKEN_EXHAUSTED   = "token_exhausted"
UNKNOWN_ERROR     = "unknown_error"

# CLI 설치 안내 (PowerShell 명령 포함)
_INSTALL_DETAIL = (
    "Claude CLI가 설치되어 있지 않습니다.\n\n"
    "아래 순서로 설치해 주세요.\n\n"
    "1. Node.js 설치 (이미 설치되어 있으면 건너뜀)\n"
    "   PowerShell에서 실행:\n"
    "   winget install OpenJS.NodeJS\n\n"
    "2. Claude Code CLI 설치\n"
    "   PowerShell에서 실행:\n"
    "   npm install -g @anthropic-ai/claude-code\n\n"
    "3. 설치 후 로그인:\n"
    "   claude\n"
    "   (브라우저가 열리면 로그인 후 앱을 재시작하세요)"
)

# stderr / stdout 에서 인증 오류를 나타내는 키워드
_AUTH_KEYWORDS = (
    "not logged in", "login required", "please log in",
    "authentication", "unauthenticated", "sign in",
    "claude auth", "run claude", "not authenticated",
    "api key", "api_key",
)

# 토큰/크레딧 소진을 나타내는 키워드
_TOKEN_KEYWORDS = (
    "credit", "credits", "quota", "exhausted", "balance",
    "usage limit", "rate limit", "insufficient", "billing",
    "overloaded", "capacity",
)


@dataclass
class ClaudeResult:
    """ask_claude 반환값. ok=True 이면 정상 응답."""
    text: str
    error_type: Optional[str] = None  # None = 정상
    detail: str = ""                  # 다이얼로그에 보여줄 상세 설명

    @property
    def ok(self) -> bool:
        return self.error_type is None


_SYSTEM_INSTRUCTION = (
    "너의 이름은 Gomis야. 답변은 3문장 이내의 간결한 구어체 한국어 존댓말로만 해. "
    "마크다운, 목록, 기호는 절대 쓰지 마. "
    "핵심만 말하고 불필요한 인사말도 빼. "
    "기온·습도·미세먼지·강수량·환율·주가 등 수치로 표현 가능한 정보는 반드시 구체적인 숫자와 단위로 답해. "
    "예: '더운 날씨' 대신 '최고 32도', '미세먼지 나쁨' 대신 'PM2.5 75㎍/㎥'. "
    "실시간 데이터가 필요한 질문(현재 날씨·주가·환율·뉴스 등)은 반드시 웹 검색을 먼저 수행하고 "
    "검색 결과에서 얻은 실제 수치로 답해. 검색 결과가 없을 때만 모른다고 말해."
)


def _detect_error_type(returncode: int, stderr: str, stdout: str) -> Optional[str]:
    combined = (stderr + stdout).lower()
    if any(k in combined for k in _AUTH_KEYWORDS):
        return NOT_AUTHENTICATED
    if any(k in combined for k in _TOKEN_KEYWORDS):
        return TOKEN_EXHAUSTED
    if returncode != 0:
        return UNKNOWN_ERROR
    return None


def ask_claude(prompt: str, timeout: int = 60) -> ClaudeResult:
    """Claude Code CLI(-p 모드)로 프롬프트 전송 → ClaudeResult 반환."""
    full_prompt = f"{_SYSTEM_INSTRUCTION}\n\n질문: {prompt}"
    log.info(f"Claude 호출: {prompt[:80]}")
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--model", "claude-haiku-4-5-20251001",
             "--allowedTools", "WebSearch"],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            creationflags=_NO_WINDOW,   # 콘솔 창 깜빡임 방지
        )
        response = result.stdout.strip()

        if result.returncode != 0:
            log.warning(f"Claude 종료코드: {result.returncode}, stderr: {result.stderr[:200]}")

        error_type = _detect_error_type(result.returncode, result.stderr, response)
        if error_type == NOT_AUTHENTICATED:
            log.warning("Claude 인증 오류 감지")
            return ClaudeResult(
                text="Claude 로그인이 필요합니다. 앱을 통해 연결해 주세요.",
                error_type=NOT_AUTHENTICATED,
                detail=(
                    "Claude CLI에 로그인되어 있지 않습니다.\n\n"
                    "PowerShell에서 아래 명령을 실행한 뒤\n"
                    "브라우저에서 로그인을 완료해 주세요:\n\n"
                    "    claude\n\n"
                    "로그인 후 Gomis를 재시작하면 정상 이용 가능합니다."
                ),
            )
        if error_type == TOKEN_EXHAUSTED:
            log.warning("Claude 토큰 소진 감지")
            return ClaudeResult(
                text="Claude 이용 한도가 초과되었습니다. 한도 초기화 이전까지 응답이 어렵습니다.",
                error_type=TOKEN_EXHAUSTED,
                detail=(
                    "Claude 계정의 토큰(크레딧)이 모두 소모되었습니다.\n\n"
                    "한도가 초기화되거나 플랜을 업그레이드한 뒤\n"
                    "다시 시도해 주세요."
                ),
            )
        if error_type == UNKNOWN_ERROR:
            log.warning(f"Claude 알 수 없는 오류: {result.stderr[:200]}")
            return ClaudeResult(
                text="Claude 응답 중 오류가 발생했습니다.",
                error_type=UNKNOWN_ERROR,
                detail=result.stderr[:400] or "알 수 없는 오류",
            )

        log.info(f"Claude 응답 ({len(response)}자): {response[:100]}")
        return ClaudeResult(text=response)

    except subprocess.TimeoutExpired:
        log.error(f"Claude 호출 타임아웃 ({timeout}초)")
        return ClaudeResult(
            text="응답 시간이 초과되었습니다.",
            error_type=UNKNOWN_ERROR,
            detail=f"Claude CLI가 {timeout}초 내에 응답하지 않았습니다.",
        )
    except FileNotFoundError:
        log.error("claude CLI를 찾을 수 없습니다.")
        return ClaudeResult(
            text="Claude CLI가 설치되어 있지 않습니다. 설치 안내를 확인해 주세요.",
            error_type=NOT_INSTALLED,
            detail=_INSTALL_DETAIL,
        )
    except Exception as e:
        log.error(f"Claude 호출 실패: {e}", exc_info=True)
        return ClaudeResult(
            text=f"오류가 발생했습니다.",
            error_type=UNKNOWN_ERROR,
            detail=str(e),
        )
