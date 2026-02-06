"""
OpenAI API 호출 로직
"""
from typing import List, Dict, Optional, Generator
from openai import OpenAI
import config
from logging_config import get_audit_logger


class ChatError(Exception):
    """채팅 관련 에러"""
    pass


def get_chat_response(
    user_message: str,
    system_prompt: str,
    conversation_history: Optional[List[Dict]] = None
) -> Generator[str, None, None]:
    """GPT 모델로부터 스트리밍 응답 생성

    Args:
        user_message: 사용자 메시지
        system_prompt: 시스템 프롬프트
        conversation_history: 대화 히스토리 [{'role': 'user', 'content': '...'}, ...]

    Yields:
        str: 각 응답 청크

    Raises:
        ChatError: API 호출 실패 시
    """
    logger = get_audit_logger()

    try:
        # OpenAI 클라이언트 초기화
        client = OpenAI(api_key=config.get_env("OPENAI_API_KEY"))

        # 메시지 구성
        messages = [{"role": "system", "content": system_prompt}]

        # 대화 히스토리 추가 (최근 10개 메시지만)
        if conversation_history:
            recent_history = conversation_history[-10:]
            messages.extend(recent_history)

        # 현재 사용자 메시지 추가
        messages.append({"role": "user", "content": user_message})

        # 스트리밍 API 호출 (gpt-5-nano는 reasoning 모델이라 충분한 토큰 필요)
        stream = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_completion_tokens=20000,
            stream=True,  # 스트리밍 활성화
            timeout=60.0  # 타임아웃 설정
        )

        # 각 청크를 yield
        chunk_count = 0
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                chunk_count += 1
                yield chunk.choices[0].delta.content

        # 빈 응답 검증
        if chunk_count == 0:
            raise ChatError("API 응답이 비어있습니다")

    except Exception as e:
        error_msg = str(e)
        logger.log_security_event(
            event_type="api_call",
            status="error",
            session_id="unknown",
            message=f"OpenAI API call failed: {error_msg}"
        )
        raise ChatError(f"AI 응답 생성 실패: {error_msg}")
