"""
Supabase 데이터베이스에 직접 연결하여 테이블 생성
psycopg2를 사용하여 PostgreSQL에 직접 SQL 실행
"""
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def create_tables():
    """PostgreSQL 직접 연결을 통한 테이블 생성"""
    try:
        # psycopg2 임포트
        try:
            import psycopg2
        except ImportError:
            print("❌ psycopg2 패키지가 설치되지 않았습니다.")
            print("   다음 명령어로 설치해주세요:")
            print("   pip install psycopg2-binary")
            return False

        # 환경변수에서 DATABASE_URL 먼저 확인
        database_url = os.getenv("DATABASE_URL")

        if database_url:
            print("🔌 DATABASE_URL 환경변수를 사용합니다.")
            conn_string = database_url
        else:
            # Supabase 연결 정보
            supabase_url = os.getenv("SUPABASE_URL")
            if not supabase_url:
                print("❌ SUPABASE_URL이 설정되지 않았습니다.")
                return False

            # URL에서 프로젝트 ID 추출
            # 예: https://msxvwxbhcvkfpvnhkiag.supabase.co
            project_id = supabase_url.replace("https://", "").replace(".supabase.co", "")

            # PostgreSQL 연결 문자열 구성
            # Supabase PostgreSQL 연결은 다음 형식을 사용합니다:
            # postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

            print(f"🔌 Supabase 프로젝트: {project_id}")
            print("\n⚠️  PostgreSQL 직접 연결을 위해서는 데이터베이스 비밀번호가 필요합니다.")
            print("\nSupabase 대시보드에서 비밀번호를 확인하는 방법:")
            print("1. https://app.supabase.com 접속")
            print("2. 프로젝트 선택")
            print("3. Settings > Database > Connection string")
            print("4. 'Connection string'에서 비밀번호 확인\n")
            print("💡 팁: .env 파일에 DATABASE_URL을 추가하면 매번 입력하지 않아도 됩니다.")
            print("   DATABASE_URL=postgresql://postgres:[비밀번호]@db.[프로젝트ID].supabase.co:5432/postgres\n")

            # 사용자에게 비밀번호 입력 받기
            import getpass
            password = getpass.getpass("PostgreSQL 비밀번호를 입력하세요 (입력 내용 숨김): ")

            if not password:
                print("❌ 비밀번호가 입력되지 않았습니다.")
                return False

            # 연결 문자열
            conn_string = f"postgresql://postgres:{password}@db.{project_id}.supabase.co:5432/postgres"

        print("\n🔌 PostgreSQL 데이터베이스에 연결 중...")
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()

        print("✅ 연결 성공!")

        # SQL 파일 읽기
        print("📄 SQL 파일 읽기 중...")
        with open('supabase_setup.sql', 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # SQL 실행
        print("🚀 테이블 생성 중...")
        cursor.execute(sql_content)
        conn.commit()

        print("✅ 테이블 생성 완료!")

        # 테이블 확인
        print("\n📊 생성된 테이블 확인 중...")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('chat_messages', 'security_events')
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        if tables:
            print("✅ 다음 테이블이 생성되었습니다:")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print("⚠️  테이블을 찾을 수 없습니다.")

        # 연결 종료
        cursor.close()
        conn.close()

        print("\n✅ 데이터베이스 설정이 완료되었습니다!")
        return True

    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Supabase 데이터베이스 테이블 생성")
    print("=" * 60)
    print()

    success = create_tables()

    print()
    print("=" * 60)

    if success:
        print("✅ 설정 완료! 이제 챗봇을 사용할 수 있습니다.")
    else:
        print("❌ 설정 실패. 위의 안내를 따라 수동으로 설정해주세요.")

    print("=" * 60)
