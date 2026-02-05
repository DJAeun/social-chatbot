"""
Streamlit 보안 챗봇 메인 애플리케이션
"""
import streamlit as st
import uuid
from typing import Optional

# 로컬 모듈
import config
from security import validate_input, SecurityException, RateLimiter
from database import get_db_client, DatabaseError
from chat import get_chat_response, ChatError
from logging_config import get_audit_logger


def init_session_state():
    """세션 상태 초기화"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "rate_limiter" not in st.session_state:
        st.session_state.rate_limiter = RateLimiter()

    if "message_count" not in st.session_state:
        st.session_state.message_count = 0

    if "agreed" not in st.session_state:
        st.session_state.agreed = False

    if "read_disclaimer" not in st.session_state:
        st.session_state.read_disclaimer = False


def load_chat_history():
    """Supabase에서 대화 히스토리 로드"""
    if st.session_state.message_count == 0:  # 첫 로드만
        try:
            db = get_db_client()
            history = db.get_history(st.session_state.session_id)
            st.session_state.chat_history = history
            st.session_state.message_count = len(history)
        except DatabaseError as e:
            st.error(f"대화 히스토리를 불러올 수 없습니다: {str(e)}")


def display_chat_history():
    """채팅 히스토리 UI 표시"""
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def process_user_input(user_input: str):
    """사용자 입력 처리 파이프라인"""
    logger = get_audit_logger()
    db = get_db_client()
    session_id = st.session_state.session_id

    try:
        # 1. 보안 검증
        sanitized_input = validate_input(
            user_input,
            session_id,
            st.session_state.rate_limiter
        )

        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(sanitized_input)

        # 히스토리에 추가
        st.session_state.chat_history.append({
            "role": "user",
            "content": sanitized_input
        })

        # DB 저장
        db.save_message(session_id, "user", sanitized_input)

        # 감사 로그
        logger.log_user_input(session_id, sanitized_input, sanitized=True)

        # 2. AI 응답 생성
        with st.spinner("답변 생성 중..."):
            system_prompt = config.get_env("SYSTEM_PROMPT")

            assistant_response = get_chat_response(
                user_message=sanitized_input,
                system_prompt=system_prompt,
                conversation_history=st.session_state.chat_history[:-1]  # 현재 메시지 제외
            )

        # 어시스턴트 응답 표시
        with st.chat_message("assistant"):
            st.markdown(assistant_response)

        # 히스토리에 추가
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": assistant_response
        })

        # DB 저장
        db.save_message(session_id, "assistant", assistant_response)

        # 성공 로그
        logger.log_api_call(session_id, success=True)

    except SecurityException as e:
        # 보안 검증 실패
        st.error(f"🚨 보안 경고: {str(e)}")

        # DB에 보안 이벤트 기록
        db.log_security_event(
            session_id=session_id,
            event_type="security_violation",
            blocked=True,
            details={"error": str(e)}
        )

        # 감사 로그
        logger.log_security_event(
            event_type="injection_detected",
            status="blocked",
            session_id=session_id,
            message=str(e)
        )

    except ChatError as e:
        # AI 응답 생성 실패
        st.error("죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

        logger.log_api_call(session_id, success=False, error_msg=str(e))

    except DatabaseError as e:
        # DB 오류
        st.error("데이터베이스 오류가 발생했습니다. 관리자에게 문의해주세요.")

        logger.log_security_event(
            event_type="error",
            status="error",
            session_id=session_id,
            message=f"Database error: {str(e)}"
        )

    except Exception as e:
        # 예상치 못한 오류
        st.error("예상치 못한 오류가 발생했습니다.")

        logger.log_security_event(
            event_type="error",
            status="error",
            session_id=session_id,
            message=f"Unexpected error: {str(e)}"
        )


def show_disclaimer_page():
    """면책조항 페이지 표시"""
    st.markdown("""
    <style>
        /* 면책조항 페이지 스타일 */
        .disclaimer-title {
            background: linear-gradient(90deg, #d92337 0%, #8b1923 100%);
            color: #ffd700;
            text-align: center;
            padding: 1.5rem;
            border-radius: 10px;
            border: 4px solid #ffd700;
            font-size: 2rem;
            font-weight: bold;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            margin-bottom: 2rem;
        }

        .stButton button {
            font-size: 1.1rem !important;
            padding: 0.75rem 2rem !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # 제목
    st.markdown('<div class="disclaimer-title">⚠️ 면책 조항 및 이용 동의 ⚠️</div>', unsafe_allow_html=True)

    # 내용
    st.markdown("### 중요한 안내사항을 반드시 읽어주세요")

    st.error("⚠️ **본 웹사이트는 패러디/장난 목적으로 제작되었습니다**")

    st.markdown("""
    **1. 정치적 의도 없음:**
    이 챗봇 인터페이스는 북한 웹사이트의 시각적 스타일을 모방한 것으로, 실제 정치적 사상이나 의견과는 **전혀 무관**합니다.

    **2. 오락 및 교육 목적:**
    본 프로젝트는 순수하게 웹 디자인 실험 및 오락 목적으로 제작되었으며, 어떠한 정치적 메시지도 담고 있지 않습니다.

    **3. 디자인 패러디:**
    사용된 색상, 레이아웃, 타이포그래피는 단순히 시각적 스타일을 모방한 것이며, 실제 정치적 입장을 표현하지 않습니다.
    """)

    st.divider()

    st.markdown("""
    **4. 책임의 한계:**
    본 챗봇 사용으로 인해 발생하는 모든 결과에 대한 책임은 사용자 본인에게 있습니다.

    **5. 데이터 수집:**
    대화 내용은 서비스 개선을 위해 저장될 수 있습니다.
    """)

    st.warning("**위 내용을 이해하고 동의하시는 경우에만 계속 진행하실 수 있습니다.**")

    st.markdown("<br>", unsafe_allow_html=True)

    # 체크박스
    read_checked = st.checkbox(
        "✅ 위 면책조항을 모두 읽었으며 내용을 이해했습니다",
        key="disclaimer_checkbox"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # 버튼
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.write("")

    with col2:
        if st.button("✅ 동의하고 계속하기", disabled=not read_checked, use_container_width=True, type="primary"):
            st.session_state.agreed = True
            st.rerun()

    with col3:
        st.write("")

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.write("")

    with col2:
        if st.button("❌ 거부하고 나가기", use_container_width=True):
            st.markdown("""
            <script>
                window.top.location.href = 'https://www.google.com';
            </script>
            """, unsafe_allow_html=True)
            st.stop()

    with col3:
        st.write("")


def apply_dprk_style():
    """북한 스타일 CSS 적용 (다크모드)"""
    st.markdown("""
    <style>
        /* 전체 배경 - 어두운 빨강에서 파랑으로 그라데이션 */
        .stApp {
            background: linear-gradient(135deg,
                #8b1923 0%,
                #6b1419 25%,
                #1e4a8a 75%,
                #0d2748 100%);
        }

        /* 메인 컨테이너 - 다크 배경 */
        .main .block-container {
            background-color: rgba(20, 20, 35, 0.95);
            border: 3px solid #d92337;
            border-radius: 0;
            padding: 2rem;
            padding-left: 180px;
            padding-bottom: 6rem;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.5);
        }

        /* 헤더 스타일 */
        h1 {
            background: linear-gradient(90deg, #d92337 0%, #8b1923 100%);
            color: #ffd700 !important;
            text-align: center;
            padding: 1.5rem;
            margin: -2rem -2rem 2rem -180px;
            border-bottom: 5px solid #ffd700;
            font-weight: bold;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            font-size: 2.5rem !important;
        }

        /* 캡션 스타일 */
        .stCaptionContainer p {
            background-color: rgba(139, 25, 35, 0.8);
            color: #ffd700;
            padding: 0.5rem 1rem;
            text-align: center;
            border-left: 4px solid #ffd700;
            border-right: 4px solid #ffd700;
            font-weight: bold;
        }

        /* 사이드바 숨기기 */
        [data-testid="stSidebar"] {
            display: none;
        }

        /* 버튼 스타일 */
        .stButton button {
            background: linear-gradient(90deg, #d92337 0%, #8b1923 100%);
            color: #ffd700;
            border: 2px solid #ffd700;
            font-weight: bold;
            border-radius: 5px;
            padding: 0.5rem 1.5rem;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.8);
        }

        .stButton button:hover {
            background: linear-gradient(90deg, #8b1923 0%, #d92337 100%);
            border-color: #ffed4e;
        }

        .stButton button:disabled {
            background: #555555 !important;
            color: #999999 !important;
            border-color: #666666 !important;
            opacity: 0.5;
        }

        /* 체크박스 스타일 */
        .stCheckbox {
            color: #ffffff !important;
        }

        .stCheckbox label {
            color: #ffffff !important;
            font-size: 1.2rem !important;
            font-weight: bold !important;
        }

        /* 채팅 메시지 공통 */
        .stChatMessage {
            border: 2px solid #d92337;
            border-radius: 8px;
        }

        /* 사용자 메시지 - 금색 배경에 검은색 텍스트 */
        .stChatMessage[data-testid*="user"] {
            background: linear-gradient(135deg, #ffd700 0%, #ffed4e 100%);
            border-color: #d92337;
        }

        .stChatMessage[data-testid*="user"] p,
        .stChatMessage[data-testid*="user"] span,
        .stChatMessage[data-testid*="user"] div {
            color: #000000 !important;
        }

        /* 어시스턴트 메시지 - 어두운 배경에 흰색 텍스트 */
        .stChatMessage[data-testid*="assistant"] {
            background: linear-gradient(135deg, #2a2a3e 0%, #1a1a2e 100%);
            border-color: #2f5da6;
        }

        .stChatMessage[data-testid*="assistant"] p,
        .stChatMessage[data-testid*="assistant"] span,
        .stChatMessage[data-testid*="assistant"] div {
            color: #ffffff !important;
        }

        /* 채팅 메시지 내용 */
        [data-testid="stChatMessageContent"] {
            background-color: transparent !important;
        }

        /* 채팅 입력창 - 다크 배경에 흰색 텍스트 */
        .stChatInput {
            border: 3px solid #d92337;
            border-radius: 5px;
        }

        .stChatInput textarea {
            border: 2px solid #ffd700 !important;
            background-color: #1a1a2e !important;
            color: #ffffff !important;
        }

        .stChatInput textarea::placeholder {
            color: #cccccc !important;
        }

        /* 스피너 */
        .stSpinner > div {
            border-top-color: #d92337 !important;
        }

        /* 에러/경고 메시지 - 다크 배경 */
        .stAlert {
            border: 2px solid #d92337;
            background-color: rgba(40, 40, 60, 0.95) !important;
            color: #ffffff !important;
        }

        .stAlert p {
            color: #ffffff !important;
        }

        /* 구분선 */
        hr {
            border-color: #ffd700;
            border-width: 2px;
        }

        /* 마크다운 텍스트 색상 */
        .main .block-container p {
            color: #ffffff;
        }

        .main .block-container h3 {
            color: #ffd700;
        }

        .main .block-container strong {
            color: #ffd700;
        }

        /* 스피너 텍스트 */
        .stSpinner > div > div {
            color: #ffffff !important;
        }
    </style>
    """, unsafe_allow_html=True)


def apply_disclaimer_style():
    """면책조항 페이지 스타일"""
    st.markdown("""
    <style>
        /* 면책조항 페이지용 스타일 */
        .main .block-container {
            padding-left: 2rem !important;
            max-width: 800px;
            margin: 0 auto;
        }

        h1 {
            margin: -2rem -2rem 2rem -2rem !important;
        }
    </style>
    """, unsafe_allow_html=True)


def main():
    """메인 애플리케이션"""

    # 페이지 설정
    st.set_page_config(
        page_title="인민의 대화봇",
        page_icon="⭐",
        layout="centered",
        initial_sidebar_state="collapsed"
    )

    # 북한 스타일 CSS 적용
    apply_dprk_style()

    # 세션 초기화
    init_session_state()

    # 동의하지 않았으면 면책조항 페이지 표시
    if not st.session_state.agreed:
        apply_disclaimer_style()
        show_disclaimer_page()
        st.stop()

    # 환경변수 검증
    try:
        config.validate_config()
    except config.ConfigurationError as e:
        st.error(f"설정 오류: {str(e)}")
        st.stop()

    # 히스토리 로드
    load_chat_history()

    # UI 레이아웃
    st.title("⭐ 인민의 대화봇 ⭐")
    st.caption(f"최대 입력 길이: {config.MAX_INPUT_LENGTH}자 | "
               f"요청 제한: {config.RATE_LIMIT_REQUESTS}회/{config.RATE_LIMIT_WINDOW}초")

    # 채팅 히스토리 표시
    display_chat_history()

    # 사용자 입력 폼
    user_input = st.chat_input(
        "메시지를 입력하세요...",
        max_chars=config.MAX_INPUT_LENGTH
    )

    if user_input:
        process_user_input(user_input)


if __name__ == "__main__":
    main()
