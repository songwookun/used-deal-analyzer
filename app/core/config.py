from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # LLM 시크릿 (.env에서 로드, 없으면 빈 문자열 → 호출 시점에 검증)
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # LLM 모델 (공개 정보, .env에서 오버라이드 가능)
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # LLM 호출 동작 파라미터 (운영 중 조정 가능)
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: float = 30.0

    # 알림 (Phase 4-a). 비면 LogNotifier (stdout) 사용.
    DISCORD_WEBHOOK_URL: str = ""

    # 네이버 데이터랩 (Phase 6). 둘 중 하나라도 비면 트렌드 기능 비활성.
    NAVER_DATALAB_CLIENT_ID: str = ""
    NAVER_DATALAB_CLIENT_SECRET: str = ""

    # 네이버 쇼핑 검색 (Phase 7). 데이터랩과 같은 키 그대로 써도 OK
    # (네이버는 같은 애플리케이션에 여러 API 권한 추가 가능). 비면 /api/search 비활성.
    NAVER_SHOP_CLIENT_ID: str = ""
    NAVER_SHOP_CLIENT_SECRET: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
