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

    model_config = {"env_file": ".env"}


settings = Settings()
