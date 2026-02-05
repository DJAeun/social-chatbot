"""
Supabase 데이터베이스 연동 모듈
"""
import os
from typing import List, Dict, Optional
from supabase import create_client, Client
from datetime import datetime
import config
from logging_config import get_audit_logger


class DatabaseError(Exception):
    """데이터베이스 에러"""
    pass


class SupabaseClient:
    """Supabase 클라이언트"""

    def __init__(self):
        """Supabase 클라이언트 초기화

        Raises:
            DatabaseError: 연결 실패 시
        """
        try:
            url = config.get_env("SUPABASE_URL")
            key = config.get_env("SUPABASE_KEY")

            if not url or not key:
                raise DatabaseError("Supabase 설정이 올바르지 않습니다")

            self.client: Client = create_client(url, key)
            self.logger = get_audit_logger()

        except Exception as e:
            raise DatabaseError(f"Supabase 연결 실패: {str(e)}")

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        """채팅 메시지 저장

        Args:
            session_id: 세션 ID
            role: 메시지 역할 ('user' or 'assistant')
            content: 메시지 내용

        Raises:
            DatabaseError: 저장 실패 시
        """
        try:
            if role not in ['user', 'assistant']:
                raise ValueError(f"Invalid role: {role}")

            data = {
                'session_id': session_id,
                'role': role,
                'content': content,
            }

            result = self.client.table('chat_messages').insert(data).execute()

            # 성공 로깅
            self.logger.log_security_event(
                event_type="database_write",
                status="success",
                session_id=session_id,
                message=f"Message saved: {role}",
                details={"content_length": len(content)}
            )

        except Exception as e:
            self.logger.log_security_event(
                event_type="database_write",
                status="error",
                session_id=session_id,
                message=f"Failed to save message: {str(e)}"
            )
            raise DatabaseError(f"메시지 저장 실패: {str(e)}")

    def get_history(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """대화 히스토리 조회

        Args:
            session_id: 세션 ID
            limit: 최대 메시지 수 (기본 50개)

        Returns:
            메시지 리스트 [{'role': 'user', 'content': '...'}, ...]

        Raises:
            DatabaseError: 조회 실패 시
        """
        try:
            response = self.client.table('chat_messages')\
                .select('role, content, created_at')\
                .eq('session_id', session_id)\
                .order('created_at', desc=False)\
                .limit(limit)\
                .execute()

            # Supabase 응답을 OpenAI 형식으로 변환
            messages = []
            if response.data:
                for row in response.data:
                    messages.append({
                        'role': row['role'],
                        'content': row['content']
                    })

            return messages

        except AttributeError as e:
            # 테이블이 없거나 응답 형식이 잘못된 경우
            self.logger.log_security_event(
                event_type="database_read",
                status="warning",
                session_id=session_id,
                message=f"Table or schema issue: {str(e)}"
            )
            return []  # 빈 리스트 반환
        except Exception as e:
            self.logger.log_security_event(
                event_type="database_read",
                status="error",
                session_id=session_id,
                message=f"Failed to get history: {str(e)}"
            )
            raise DatabaseError(f"히스토리 조회 실패: {str(e)}")

    def log_security_event(
        self,
        session_id: str,
        event_type: str,
        blocked: bool,
        details: Optional[Dict] = None
    ) -> None:
        """보안 이벤트 DB 기록

        Args:
            session_id: 세션 ID
            event_type: 이벤트 유형
            blocked: 차단 여부
            details: 추가 상세 정보
        """
        try:
            data = {
                'session_id': session_id,
                'event_type': event_type,
                'blocked': blocked,
                'details': details or {}
            }

            self.client.table('security_events').insert(data).execute()

        except Exception as e:
            # 보안 이벤트 로깅 실패는 치명적이지 않으므로 경고만 출력
            self.logger.log_security_event(
                event_type="database_write",
                status="error",
                session_id=session_id,
                message=f"Failed to log security event: {str(e)}"
            )

    def get_security_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """보안 이벤트 조회

        Args:
            session_id: 세션 ID (선택)
            event_type: 이벤트 유형 (선택)
            limit: 최대 이벤트 수

        Returns:
            보안 이벤트 리스트
        """
        try:
            query = self.client.table('security_events').select('*')

            if session_id:
                query = query.eq('session_id', session_id)
            if event_type:
                query = query.eq('event_type', event_type)

            response = query.order('created_at', desc=True)\
                .limit(limit)\
                .execute()

            return response.data

        except Exception as e:
            raise DatabaseError(f"보안 이벤트 조회 실패: {str(e)}")


# 전역 인스턴스
_db_client: Optional[SupabaseClient] = None


def get_db_client() -> SupabaseClient:
    """싱글톤 DB 클라이언트 가져오기

    Returns:
        SupabaseClient 인스턴스
    """
    global _db_client
    if _db_client is None:
        _db_client = SupabaseClient()
    return _db_client
