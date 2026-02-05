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
            # 데이터베이스 오류 시 빈 히스토리로 시작
            st.session_state.chat_history = []
            st.session_state.message_count = 0
            logger = get_audit_logger()
            logger.log_security_event(
                event_type="error",
                status="error",
                session_id=st.session_state.session_id,
                message=f"Failed to load chat history: {str(e)}"
            )
        except Exception as e:
            # 예상치 못한 오류도 처리
            st.session_state.chat_history = []
            st.session_state.message_count = 0
            logger = get_audit_logger()
            logger.log_security_event(
                event_type="error",
                status="error",
                session_id=st.session_state.session_id,
                message=f"Unexpected error loading chat history: {str(e)}"
            )


def display_chat_history():
    """채팅 히스토리 UI 표시"""
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def stream_and_collect(generator, loading_placeholder=None):
    """스트림 청크를 수집하면서 yield하는 래퍼

    Args:
        generator: 원본 제너레이터
        loading_placeholder: 첫 청크 시 제거할 st.empty() 객체 (선택)

    Yields:
        str: 각 청크
    """
    collected = []
    first_chunk = True

    for chunk in generator:
        # 첫 번째 청크 도착 시 로딩 인디케이터 제거
        if first_chunk and loading_placeholder is not None:
            loading_placeholder.empty()
            first_chunk = False

        collected.append(chunk)
        yield chunk

    # 전체 응답을 함수 속성으로 저장
    stream_and_collect.full_response = "".join(collected)


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

        # 2. AI 응답 생성 및 스트리밍 표시
        system_prompt = config.get_env("SYSTEM_PROMPT")

        with st.chat_message("assistant"):
            try:
                # 로딩 인디케이터 표시
                loading_placeholder = st.empty()
                loading_placeholder.markdown("⚒️ 공산당 가입 중...")

                # 스트리밍 제너레이터 생성
                stream_generator = get_chat_response(
                    user_message=sanitized_input,
                    system_prompt=system_prompt,
                    conversation_history=st.session_state.chat_history[:-1]  # 현재 메시지 제외
                )

                # 래퍼로 감싸서 전체 응답 수집 + 로딩 인디케이터 제거
                wrapped_stream = stream_and_collect(stream_generator, loading_placeholder)

                # Streamlit으로 스트리밍 표시
                st.write_stream(wrapped_stream)

                # 전체 응답 가져오기
                assistant_response = stream_and_collect.full_response

            except ChatError as e:
                # 스트리밍 중 오류 발생
                loading_placeholder.empty()  # 로딩 인디케이터 제거
                st.error(f"❌ {str(e)}")
                logger.log_api_call(session_id, success=False, error_msg=str(e))
                return  # DB에 저장하지 않고 종료

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
        st.error("데이터베이스 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

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

        /* 면책조항 내용 박스 */
        .disclaimer-content {
            background-color: rgba(20, 20, 35, 0.95);
            border: 3px solid #d92337;
            border-radius: 10px;
            padding: 2rem;
            margin-bottom: 2rem;
        }

        .disclaimer-content p,
        .disclaimer-content li {
            color: #ffffff !important;
        }

        .disclaimer-content strong {
            color: #ffd700 !important;
        }

        .stButton button {
            font-size: 1.1rem !important;
            padding: 0.75rem 2rem !important;
            height: 60px !important;
            min-height: 60px !important;
        }

        /* link_button도 동일한 크기로 */
        .stLinkButton a {
            font-size: 1.1rem !important;
            padding: 0.75rem 2rem !important;
            height: 60px !important;
            min-height: 60px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # 제목
    st.markdown('<div class="disclaimer-title">⚠️ 면책 조항 및 이용 동의 ⚠️</div>', unsafe_allow_html=True)

    # 내용 - 하나의 박스로 감싸기
    st.markdown("""
    <div class="disclaimer-content">
    <h3 style="color: #ffd700;">중요한 안내사항을 반드시 읽어주세요</h3>

    <div style="background: linear-gradient(90deg, #d92337 0%, #8b1923 100%); color: #ffd700; padding: 1rem; border-radius: 5px; margin-bottom: 1.5rem; border: 2px solid #ffd700;">
        ⚠️ <strong>본 웹사이트는 패러디/장난 목적으로 제작되었습니다</strong>
    </div>

    <p><strong>1. 정치적 의도 없음:</strong><br>
    이 챗봇 인터페이스는 북한 웹사이트의 시각적 스타일을 모방한 것으로, 실제 정치적 사상이나 의견과는 <strong>전혀 무관</strong>합니다.</p>

    <p><strong>2. 오락 및 교육 목적:</strong><br>
    본 프로젝트는 순수하게 웹 디자인 실험 및 오락 목적으로 제작되었으며, 어떠한 정치적 메시지도 담고 있지 않습니다.</p>

    <p><strong>3. 디자인 패러디:</strong><br>
    사용된 색상, 레이아웃, 타이포그래피는 단순히 시각적 스타일을 모방한 것이며, 실제 정치적 입장을 표현하지 않습니다.</p>

    <p><strong>4. 책임의 한계:</strong><br>
    본 챗봇 사용으로 인해 발생하는 모든 결과에 대한 책임은 사용자 본인에게 있습니다.</p>

    <p><strong>5. 데이터 수집:</strong><br>
    대화 내용은 서비스 개선을 위해 저장될 수 있습니다.</p>

    <div style="background: linear-gradient(90deg, #8b6914 0%, #5c4610 100%); color: #ffd700; padding: 1rem; border-radius: 5px; margin-top: 1.5rem; border: 2px solid #ffd700;">
        <strong>위 내용을 이해하고 동의하시는 경우에만 계속 진행하실 수 있습니다.</strong>
    </div>
    <br>
    <p>프롬프트 인젝션을 통해 내부 정보를 빼내거나 <em>자본주의 괴뢰</em> 의 사상을 주입해보세요!</p>

    <p>성공했다면 <strong>보안 기술의 발전</strong>을 위해 인증해주세요!</p>
    </div>
    """, unsafe_allow_html=True)

    # 체크박스
    read_checked = st.checkbox(
        "✅ 위 면책조항을 모두 읽었으며 내용을 이해했습니다",
        key="disclaimer_checkbox"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # 버튼 - 좌우 배치
    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ 동의하고 계속하기", disabled=not read_checked, use_container_width=True, type="primary"):
            st.session_state.agreed = True
            st.rerun()

    with col2:
        st.link_button("❌ 거부하고 나가기", "https://www.google.com", use_container_width=True)


def apply_dprk_style():
    """북한 스타일 CSS 적용 (다크모드)"""
    st.markdown("""
    <style>
        /* 전체 배경 - 공산주의 상징 이미지 */
        .stApp {
            background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMjAwIiBoZWlnaHQ9IjYwMCI+PHBhdGggZD0iTTAgMGgxMjAwdjYwMEgweiIgc3R5bGU9ImZpbGw6I2Q0MDAwMCIvPjxwYXRoIGQ9Ik02MDAgMTAwYy0xMS40NzIgMjYuNDc0LTE5LjMxNiAzOS4xOTctMjIuOTQ1IDU1LjIyLTcuODYzIDM0LjcyIDguNTE1IDYzLjA2MyA4LjUxNSA2My4wNjNsLjAxLjAwNmgtNS4xMDN2MTE1LjEwNmwtNzguNDQyLTc5LjEzNyA0Ni45OTItNDYuNTgtMTguODMyLTE4Ljk5OC0zOC41MTEuNTA2LTI3LjMxNSAyNy4wNzQtOS40NDEtOS41MjYtMjcuNjk4IDI3LjQ1NCA5LjQ0MiA5LjUyNS0yNi4xNTQgMjUuOTI2IDM3LjY2NiAzOCAyNi4xNTYtMjUuOTI2IDk4LjE5MyA5OS4wNi02OS42NzIgNzAuMjc2IDI3LjcwNSAyNy40NjcgNDkuOTEtNTAuMzU0VjUwMGgzOC45OTl2LTcxLjg3bDQ5LjkyIDUwLjM2MiAyNy42OTctMjcuNDUzLTY5LjY0Ny03MC4yNjQgMTAzLjM3MS0xMDQuMjg5LTIuMTM0LTIuMTEzYzE3LjMyOSAxLjk1IDM0LjQ2LS4yMzUgNDEuNTc4LTguNjEzIDkuNDA4LTExLjA3NCAxMC4yMzMtMzEuMDggMS4wMS00NS4zMTMtMjcuNC00Mi4yOC04NC41NDYtNDcuNzYyLTExMS40MDUtNDcuODYxLTguOTUzLS4wMzMtMTQuNTI1LjUzLTE0LjUyNS41M3MxMzMuMzU2IDUyLjUxMyA2MS4zMDggNzkuNDU0bC0zLjUzOS0zLjUwMi04My42MzQgODQuMzZWMjE4LjI4OWgtNS4xMDJsLjAxLS4wMDZzMTYuMzc2LTI4LjM0MyA4LjUxMy02My4wNjJDNjE5LjI2OCAxMzkuMTk3IDYxMS40NzIgMTI2LjQ3NCA2MDAgMTAwWiIgc3R5bGU9ImZpbGw6I2ZjMCIvPjwvc3ZnPg==");
            background-size: cover;
            background-position: center;
            background-repeat: repeat;
            background-attachment: fixed;
        }

        /* 메인 컨테이너 - 다크 배경 */
        .main .block-container {
            background-color: rgba(20, 20, 35, 0.95) !important;
            border: 3px solid #d92337 !important;
            border-radius: 0;
            padding: 2rem !important;
            padding-bottom: 6rem !important;
            max-width: 900px;
            margin: 0 auto;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.5);
        }

        /* 헤더 스타일 */
        h1 {
            background: linear-gradient(90deg, #d92337 0%, #8b1923 100%);
            color: #ffd700 !important;
            text-align: center;
            padding: 1.5rem;
            margin: -2rem -2rem 2rem -2rem;
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
            max-width: 100%;
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
        .stChatMessage:has([data-testid="chatAvatarIcon-assistant"]),
        [data-testid="stChatMessage"]:nth-child(even),
        .stChatMessage:not(:has([data-testid="chatAvatarIcon-user"])) {
            background: rgba(30, 30, 50, 0.98) !important;
            border: 2px solid #2f5da6 !important;
            border-radius: 8px !important;
        }

        .stChatMessage:has([data-testid="chatAvatarIcon-assistant"]) *,
        .stChatMessage:not(:has([data-testid="chatAvatarIcon-user"])) p,
        .stChatMessage:not(:has([data-testid="chatAvatarIcon-user"])) span,
        .stChatMessage:not(:has([data-testid="chatAvatarIcon-user"])) div,
        .stChatMessage:not(:has([data-testid="chatAvatarIcon-user"])) li {
            color: #ffffff !important;
            background: transparent !important;
        }

        /* 채팅 메시지 내용 - 배경 통일 */
        [data-testid="stChatMessageContent"] {
            background-color: transparent !important;
        }

        /* 마크다운 컨텐츠 배경 투명화 */
        .stChatMessage .stMarkdown,
        .stChatMessage [data-testid="stMarkdownContainer"] {
            background: transparent !important;
        }

        /* 채팅 입력창 - 다크 배경에 흰색 텍스트 */
        .stChatInput {
            border: 3px solid #d92337;
            border-radius: 5px;
            max-width: 900px;
            margin: 0 auto;
        }

        .stChatInput textarea {
            border: 2px solid #ffd700 !important;
            background-color: #1a1a2e !important;
            color: #ffffff !important;
        }

        .stChatInput textarea::placeholder {
            color: #cccccc !important;
        }

        /* 채팅 입력창을 하단에 고정 */
        .stChatInputContainer {
            max-width: 900px;
            margin: 0 auto;
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
        /* 면책조항 페이지용 스타일 - 전체 컨테이너 배경 */
        .main .block-container {
            max-width: 800px;
            margin: 0 auto;
            background-color: rgba(20, 20, 35, 0.95) !important;
            border-radius: 15px;
            padding: 2rem !important;
            border: 3px solid #d92337;
        }

        /* 마크다운 요소 배경 제거 - 전체 면으로 통일 */
        .stMarkdown,
        [data-testid="stMarkdownContainer"] {
            background-color: transparent !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        h1 {
            margin: -2rem -2rem 2rem -2rem !important;
        }

        /* 면책조항 내용 텍스트 가독성 향상 */
        .main .block-container p,
        .main .block-container li,
        .main .block-container h3 {
            color: #ffffff !important;
        }

        .main .block-container strong {
            color: #ffd700 !important;
        }

        /* 체크박스 라벨 */
        .stCheckbox label {
            color: #ffffff !important;
        }

        .stCheckbox label span {
            color: #ffd700 !important;
        }

        /* 구분선 스타일 */
        hr {
            border-color: #d92337 !important;
        }
    </style>
    """, unsafe_allow_html=True)


def main():
    """메인 애플리케이션"""

    # 페이지 설정
    st.set_page_config(
        page_title="인민의 대화",
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
        st.error("서버 설정 오류가 발생했습니다. 관리자에게 문의해주세요.")
        # 실제 에러는 로그에만 기록
        logger = get_audit_logger()
        logger.log_security_event(
            event_type="error",
            status="error",
            session_id=st.session_state.session_id,
            message=f"Configuration error: {str(e)}"
        )
        st.stop()

    # 히스토리 로드
    load_chat_history()

    # UI 레이아웃
    st.title("⭐ 인민의 대화 ⭐")
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
