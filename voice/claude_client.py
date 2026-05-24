"""
Claude Code CLI subprocess 호출 모듈.
`claude -p "prompt"` 로 응답 텍스트를 반환한다.
"""
import logging
import subprocess

log = logging.getLogger("voice")


_SYSTEM_INSTRUCTION = (
    "답변은 3문장 이내의 간결한 구어체 한국어 존댓말로만 해. "
    "마크다운, 목록, 기호는 절대 쓰지 마. "
    "핵심만 말하고 불필요한 인사말도 빼."
)


def ask_claude(prompt: str, timeout: int = 60) -> str:
    """Claude Code CLI(-p 모드)로 프롬프트 전송 → 응답 텍스트 반환."""
    full_prompt = f"{_SYSTEM_INSTRUCTION}\n\n질문: {prompt}"
    log.info(f"Claude 호출: {prompt[:80]}")
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
        response = result.stdout.strip()
        if result.returncode != 0:
            log.warning(f"Claude 종료코드: {result.returncode}, stderr: {result.stderr[:200]}")
        log.info(f"Claude 응답 ({len(response)}자): {response[:100]}")
        return response
    except subprocess.TimeoutExpired:
        log.error(f"Claude 호출 타임아웃 ({timeout}초)")
        return "응답 시간이 초과되었습니다."
    except FileNotFoundError:
        log.error("claude CLI를 찾을 수 없습니다.")
        return "Claude CLI를 찾을 수 없습니다. Claude Code 설치 여부를 확인하세요."
    except Exception as e:
        log.error(f"Claude 호출 실패: {e}", exc_info=True)
        return f"오류가 발생했습니다: {e}"
