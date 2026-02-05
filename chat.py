"""
LangChain + LangSmith 통합 LLM 호출 로직
"""
from typing import List, Dict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import config
from logging_config import get_audit_logger


class ChatError(Exception):
    """채팅 관련 에러"""
    pass


def _convert_dict_to_langchain_messages(
    messages_dict: List[Dict]
) -> List:
    """Dict 형태 메시지를 LangChain Message 객체로 변환

    Args:
        messages_dict: [{'role': 'user', 'content': '...'}, ...]

    Returns:
        LangChain Message 객체 리스트
    """
    langchain_messages = []

    for msg in messages_dict:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            langchain_messages.append(SystemMessage(content=content))
        elif role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))
        else:
            # 알 수 없는 role은 무시하거나 HumanMessage로 처리
            langchain_messages.append(HumanMessage(content=content))

    return langchain_messages


def get_chat_response(
    user_message: str,
    system_prompt: str,
    conversation_history: Optional[List[Dict]] = None
) -> str:
    """LangChain을 통해 GPT 모델로부터 응답 생성

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
        # LangChain ChatOpenAI 초기화
        llm = ChatOpenAI(
            model="gpt-5-nano",
            api_key=config.get_env("OPENAI_API_KEY"),
            max_tokens=40000,
            temperature=1.0,
        )

        # 메시지 구성 (Dict → LangChain Messages)
        messages = [SystemMessage(content=system_prompt)]

        # 대화 히스토리 추가 (최근 10개 메시지만)
        if conversation_history:
            recent_history = conversation_history[-10:]
            history_messages = _convert_dict_to_langchain_messages(recent_history)
            messages.extend(history_messages)

        # 현재 사용자 메시지 추가
        messages.append(HumanMessage(content=user_message))

        # LangChain invoke 호출 (LangSmith 자동 추적)
        response = llm.invoke(messages)

        # 응답 추출
        assistant_message = response.content

        if not assistant_message:
            raise ChatError("API 응답이 비어있습니다")

        return assistant_message

    except Exception as e:
        error_msg = str(e)
        logger.log_security_event(
            event_type="api_call",
            status="error",
            session_id="unknown",
            message=f"LangChain API call failed: {error_msg}"
        )
        raise ChatError(f"AI 응답 생성 실패: {error_msg}")
