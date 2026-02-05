"""
감사 로깅 모듈
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib


class AuditLogger:
    """보안 이벤트 감사 로깅"""

    def __init__(self, log_dir: str = "logs"):
        """로거 초기화

        Args:
            log_dir: 로그 디렉토리 경로
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # JSON Lines 형식 로거 설정
        self.logger = logging.getLogger("audit_logger")
        self.logger.setLevel(logging.INFO)

        # 핸들러가 없을 때만 추가 (중복 방지)
        if not self.logger.handlers:
            handler = logging.FileHandler(
                self.log_dir / "audit.log",
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    @staticmethod
    def hash_session_id(session_id: str) -> str:
        """세션 ID 해시화 (개인정보 보호)

        Args:
            session_id: 원본 세션 ID

        Returns:
            SHA256 해시값 (앞 16자)
        """
        return hashlib.sha256(session_id.encode()).hexdigest()[:16]

    @staticmethod
    def mask_sensitive_data(text: str) -> str:
        """민감정보 마스킹

        Args:
            text: 원본 텍스트

        Returns:
            마스킹된 텍스트
        """
        # API 키 마스킹
        text = re.sub(r'sk-[a-zA-Z0-9]{20,}', 'sk-***MASKED***', text)

        # 비밀번호 마스킹
        text = re.sub(
            r'(password|passwd|pwd)\s*[=:\'"\s]+[\w!@#$%^&*]{8,}',
            r'\1=***MASKED***',
            text,
            flags=re.IGNORECASE
        )

        # 카드번호 마스킹
        text = re.sub(
            r'\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b',
            r'\1-****-****-\4',
            text
        )

        return text

    def log_security_event(
        self,
        event_type: str,
        status: str,
        session_id: str,
        message: str,
        details: Optional[dict] = None
    ) -> None:
        """보안 이벤트 로깅

        Args:
            event_type: 이벤트 유형 ('user_input', 'injection_detected',
                        'rate_limit_exceeded', 'api_call', 'error')
            status: 상태 ('success', 'blocked', 'error')
            session_id: 세션 ID
            message: 로그 메시지
            details: 추가 상세 정보
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session_id": self.hash_session_id(session_id),
            "event_type": event_type,
            "status": status,
            "message": self.mask_sensitive_data(message),
        }

        if details:
            # 상세 정보도 마스킹
            masked_details = {
                k: self.mask_sensitive_data(str(v)) if isinstance(v, str) else v
                for k, v in details.items()
            }
            log_entry["details"] = masked_details

        # JSON Lines 형식으로 기록
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))

    def log_user_input(self, session_id: str, input_text: str, sanitized: bool = True) -> None:
        """사용자 입력 로깅

        Args:
            session_id: 세션 ID
            input_text: 입력 텍스트 (마스킹 전)
            sanitized: 샌더타이징 성공 여부
        """
        self.log_security_event(
            event_type="user_input",
            status="success" if sanitized else "blocked",
            session_id=session_id,
            message=f"User input: {input_text[:50]}..." if len(input_text) > 50 else f"User input: {input_text}",
            details={"length": len(input_text)}
        )

    def log_api_call(self, session_id: str, success: bool, error_msg: Optional[str] = None) -> None:
        """API 호출 로깅

        Args:
            session_id: 세션 ID
            success: 성공 여부
            error_msg: 에러 메시지 (실패 시)
        """
        self.log_security_event(
            event_type="api_call",
            status="success" if success else "error",
            session_id=session_id,
            message="OpenAI API call completed" if success else f"API call failed: {error_msg}"
        )


# 전역 인스턴스
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """싱글톤 감사 로거 가져오기

    Returns:
        AuditLogger 인스턴스
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
