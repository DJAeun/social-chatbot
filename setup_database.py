"""
Supabase 데이터베이스 초기 설정 스크립트
supabase_setup.sql의 SQL을 실행하여 테이블을 생성합니다.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def setup_database():
    """데이터베이스 테이블 생성"""
    try:
        # Supabase 클라이언트 생성
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            print("❌ SUPABASE_URL 또는 SUPABASE_KEY가 설정되지 않았습니다.")
            print("   .env 파일을 확인해주세요.")
            return False

        print(f"🔌 Supabase 연결 중... ({url})")
        client: Client = create_client(url, key)

        # SQL 파일 읽기
        with open('supabase_setup.sql', 'r', encoding='utf-8') as f:
            sql_content = f.read()

        print("📄 SQL 파일을 읽었습니다.")

        # SQL 실행
        # 주의: supabase-py는 raw SQL 실행을 직접 지원하지 않습니다.
        # 대신 REST API를 통해 실행해야 합니다.

        print("\n⚠️  주의: Python 클라이언트는 raw SQL 실행을 지원하지 않습니다.")
        print("다음 방법 중 하나를 사용해주세요:\n")
        print("1️⃣  Supabase 대시보드 사용 (권장):")
        print("   - https://app.supabase.com 접속")
        print("   - 프로젝트 선택")
        print("   - 좌측 메뉴: SQL Editor")
        print("   - supabase_setup.sql 내용 붙여넣기 후 실행\n")
        print("2️⃣  Supabase CLI 사용:")
        print("   supabase db reset\n")
        print("3️⃣  psql 사용 (PostgreSQL 클라이언트):")
        print("   - Supabase 프로젝트 설정에서 Database URL 확인")
        print("   - psql을 사용하여 직접 연결\n")

        # 테이블 존재 여부 확인
        print("📊 현재 테이블 상태 확인 중...")
        try:
            result = client.table('chat_messages').select("count", count='exact').limit(0).execute()
            print("✅ chat_messages 테이블이 존재합니다.")
            return True
        except Exception as e:
            if 'PGRST205' in str(e) or 'not found' in str(e).lower():
                print("❌ chat_messages 테이블이 존재하지 않습니다.")
                print("\n위의 방법 중 하나를 사용하여 테이블을 생성해주세요.")
            else:
                print(f"❌ 테이블 확인 중 오류: {str(e)}")
            return False

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Supabase 데이터베이스 설정")
    print("=" * 60)
    print()

    setup_database()

    print()
    print("=" * 60)
