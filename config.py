"""
환경변수 및 상수 관리 모듈
"""
import os
from dotenv import load_dotenv
from typing import Optional


class ConfigurationError(Exception):
    """설정 관련 에러"""
    pass


# 보안 상수
MAX_INPUT_LENGTH = 500 # 글자
RATE_LIMIT_REQUESTS = 1 # 번
RATE_LIMIT_WINDOW = 20  # 초


def load_env_vars() -> None:
    """환경변수 로드"""
    load_dotenv()


def get_env(key: str, required: bool = True) -> Optional[str]:
    """환경변수 조회 (Streamlit Cloud와 로컬 환경 모두 지원)

    Args:
        key: 환경변수 키
        required: 필수 여부

    Returns:
        환경변수 값

    Raises:
        ConfigurationError: 필수 환경변수가 없을 때
    """
    # 1. Streamlit secrets 확인 (Streamlit Cloud 배포 시)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except (ImportError, FileNotFoundError, KeyError):
        pass

    # 2. 환경변수 확인 (로컬 개발 시)
    value = os.getenv(key)
    if required and not value:
        raise ConfigurationError(f"필수 환경변수가 설정되지 않았습니다: {key}")
    return value


def validate_config() -> None:
    """필수 환경변수 검증

    Raises:
        ConfigurationError: 필수 환경변수가 없을 때
    """
    required_vars = [
        "OPENAI_API_KEY",
        "SYSTEM_PROMPT",
        "SUPABASE_URL",
        "SUPABASE_KEY"
    ]

    missing_vars = []
    for var in required_vars:
        if not get_env(var, required=False):  # Streamlit secrets와 환경변수 모두 확인
            missing_vars.append(var)

    if missing_vars:
        raise ConfigurationError(
            f"다음 필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}"
        )


# 모듈 임포트 시 자동 로드
load_env_vars()
