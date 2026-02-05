"""
보안 계층 모듈 - 5가지 핵심 보안 기능 구현
"""
import re
import bleach
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import config


class SecurityException(Exception):
    """보안 검증 실패 예외"""
    pass


class InputSanitizer:
    """HTML/JavaScript 태그 제거"""

    @staticmethod
    def sanitize_html(text: str) -> str:
        """HTML 태그 제거 및 길이 검증

        Args:
            text: 입력 텍스트

        Returns:
            샌더타이징된 텍스트

        Raises:
            SecurityException: 입력이 너무 길 때
        """
        if len(text) > config.MAX_INPUT_LENGTH:
            raise SecurityException(
                f"입력이 너무 깁니다. 최대 {config.MAX_INPUT_LENGTH}자까지 가능합니다."
            )

        # 모든 HTML 태그 제거
        sanitized = bleach.clean(
            text,
            tags=[],  # 모든 태그 제거
            strip=True  # 태그 내용은 유지
        )

        return sanitized.strip()


class PromptInjectionDetector:
    """프롬프트 인젝션 공격 패턴 감지"""

    # 패턴 사전 컴파일 (성능 최적화)
    INJECTION_PATTERNS = [
        # 영어 패턴
        (re.compile(r'(?i)ignore\s+(previous|all|prior|initial|original)\s+(prompt|instruction|rule|directive)', re.IGNORECASE), 'ignore_instruction'),
        (re.compile(r'(?i)forget\s+(previous|all|prior|initial|original)\s+(prompt|instruction|rule|directive)', re.IGNORECASE), 'forget_instruction'),
        (re.compile(r'(?i)(system|admin)\s*(prompt|override|mode|command)', re.IGNORECASE), 'system_override'),
        (re.compile(r'(?i)jailbreak', re.IGNORECASE), 'jailbreak'),
        (re.compile(r'(?i)(act|behave|pretend)\s+as\s+(hacker|admin|root|superuser|developer)', re.IGNORECASE), 'role_manipulation'),
        (re.compile(r'(?i)(reveal|show|tell|display|what\s+is)\s+(your\s+)?(system\s+)?(prompt|instruction|directive|rule)', re.IGNORECASE), 'prompt_extraction'),
        (re.compile(r'(?i)disregard\s+(previous|all|safety|rules|instructions)', re.IGNORECASE), 'disregard_safety'),
        (re.compile(r'(?i)(what|show|reveal|tell).{0,20}(system\s+)?(prompt|instruction)', re.IGNORECASE), 'prompt_inquiry'),
        (re.compile(r'(?i)you\s+are\s+now', re.IGNORECASE), 'role_override'),
        (re.compile(r'(?i)(override|bypass|disable)\s+(security|safety|filter|restriction)', re.IGNORECASE), 'security_bypass'),

        # 한글 패턴
        (re.compile(r'(무시|잊어|삭제|제거).{0,10}(프롬프트|지시|명령|규칙|설정)'), 'ignore_instruction_kr'),
        (re.compile(r'(프롬프트|시스템\s*프롬프트|초기\s*지시|지시사항|설정).{0,20}(알려|보여|공개|노출|말해|뭐야|무엇|내용)'), 'prompt_extraction_kr'),
        (re.compile(r'(현재|지금|당신의|너의).{0,10}(프롬프트|지시사항|설정|명령).{0,20}(알려|보여|말해|뭐야|무엇)'), 'prompt_inquiry_kr'),
        (re.compile(r'(이전|기존|원래).{0,10}(프롬프트|지시|명령|규칙).{0,10}(무시|잊어|삭제)'), 'forget_instruction_kr'),
        (re.compile(r'(개발자|관리자|시스템|루트)\s*(모드|권한|명령)'), 'admin_mode_kr'),
        (re.compile(r'이제부터.{0,20}(역할|행동|대답)'), 'role_override_kr'),
        (re.compile(r'(보안|안전|필터|제한).{0,10}(우회|비활성화|해제|무시)'), 'security_bypass_kr'),
    ]

    @classmethod
    def detect(cls, text: str) -> Optional[str]:
        """프롬프트 인젝션 패턴 감지

        Args:
            text: 검사할 텍스트

        Returns:
            감지된 공격 유형 (없으면 None)
        """
        for pattern, attack_type in cls.INJECTION_PATTERNS:
            if pattern.search(text):
                return attack_type
        return None


class SensitiveDataFilter:
    """민감정보 패턴 탐지"""

    # 패턴 사전 컴파일
    SENSITIVE_PATTERNS = {
        'api_key': re.compile(r'(sk-[a-zA-Z0-9]{20,}|OPENAI_API_KEY|api[_-]?key\s*[=:]\s*[\'"][^\'"]+[\'"])', re.IGNORECASE),
        'password': re.compile(r'(password|passwd|pwd)\s*[=:\'"]\s*[\w!@#$%^&*]{8,}', re.IGNORECASE),
        'credit_card': re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),
        'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),  # 주민번호 유사 패턴
        'email_password': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\s+(password|passwd)\s*[=:]\s*\S+', re.IGNORECASE),
    }

    @classmethod
    def has_sensitive_data(cls, text: str) -> Optional[str]:
        """민감정보 존재 여부 확인

        Args:
            text: 검사할 텍스트

        Returns:
            감지된 민감정보 유형 (없으면 None)
        """
        for data_type, pattern in cls.SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                return data_type
        return None


class RateLimiter:
    """세션 기반 요청 속도 제한"""

    def __init__(self):
        """Rate limiter 초기화"""
        self.request_history: Dict[str, List[datetime]] = {}

    def check_rate_limit(self, session_id: str) -> bool:
        """요청 속도 제한 확인

        Args:
            session_id: 세션 ID

        Returns:
            True if 제한 초과, False if 정상
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=config.RATE_LIMIT_WINDOW)

        # 세션의 요청 이력 가져오기
        if session_id not in self.request_history:
            self.request_history[session_id] = []

        # 윈도우 내 요청만 필터링
        recent_requests = [
            req_time for req_time in self.request_history[session_id]
            if req_time > window_start
        ]

        # 제한 확인
        if len(recent_requests) >= config.RATE_LIMIT_REQUESTS:
            return True  # 제한 초과

        # 현재 요청 추가
        recent_requests.append(now)
        self.request_history[session_id] = recent_requests

        return False  # 정상


def validate_input(user_input: str, session_id: str, rate_limiter: RateLimiter) -> str:
    """통합 입력 검증 파이프라인

    검증 순서:
    1. 길이 검증
    2. HTML 샌더타이징
    3. 프롬프트 인젝션 탐지
    4. 민감정보 필터링
    5. Rate limit 확인

    Args:
        user_input: 사용자 입력
        session_id: 세션 ID
        rate_limiter: RateLimiter 인스턴스

    Returns:
        샌더타이징된 입력값

    Raises:
        SecurityException: 검증 실패 시
    """
    # 1. Rate limit 확인 (가장 먼저)
    if rate_limiter.check_rate_limit(session_id):
        raise SecurityException(
            f"요청 횟수 제한을 초과했습니다. {config.RATE_LIMIT_WINDOW}초 후 다시 시도해주세요."
        )

    # 2. 길이 검증 및 HTML 샌더타이징
    sanitized_input = InputSanitizer.sanitize_html(user_input)

    # 3. 프롬프트 인젝션 탐지
    injection_type = PromptInjectionDetector.detect(sanitized_input)
    if injection_type:
        raise SecurityException(
            f"보안 위협이 감지되었습니다. 입력을 확인해주세요."
        )

    # 4. 민감정보 필터링
    sensitive_type = SensitiveDataFilter.has_sensitive_data(sanitized_input)
    if sensitive_type:
        raise SecurityException(
            "민감한 정보가 포함되어 있습니다. API 키, 비밀번호 등을 입력하지 마세요."
        )

    return sanitized_input
