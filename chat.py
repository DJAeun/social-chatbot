"""
OpenAI API 호출 로직
"""
from typing import List, Dict, Optional
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
) -> str:
    """GPT 모델로부터 응답 생성

    Args:
        user_message: 사용자 메시지
        system_prompt: 시스템 프롬프트
        conversation_history: 대화 히스토리 [{'role': 'user', 'content': '...'}, ...]

    Returns:
        어시스턴트 응답 텍스트

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

        # API 호출
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        # 응답 추출
        assistant_message = response.choices[0].message.content

        if not assistant_message:
            raise ChatError("API 응답이 비어있습니다")

        return assistant_message

    except Exception as e:
        error_msg = str(e)
        logger.log_security_event(
            event_type="api_call",
            status="error",
            session_id="unknown",
            message=f"OpenAI API call failed: {error_msg}"
        )
        raise ChatError(f"AI 응답 생성 실패: {error_msg}")
