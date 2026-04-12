from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    [요구사항]

    1. DATABASE_URL 필드를 선언해주세요
       - 타입: str
       - 기본값: "sqlite+aiosqlite:///./dev.db"
       - .env 파일에서 자동으로 읽어옵니다
    """
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"
    """
    2. model_config 설정
       - env_file = ".env" 로 설정해주세요
       - 이러면 .env 파일의 DATABASE_URL 값을 자동으로 가져옵니다
    """
    model_config = {
        "env_file": ".env"
    }

# 앱 전체에서 쓸 settings 인스턴스를 하나 만들어주세요
# 변수명: settings
# 예: 다른 파일에서 from app.core.config import settings 로 가져다 씁니다
settings = Settings()
