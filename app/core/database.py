from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings


"""
[요구사항]

1. engine 생성
   - create_async_engine()을 사용해주세요
   - 첫 번째 인자: settings.DATABASE_URL
   - echo=True 옵션 추가 (실행되는 SQL을 콘솔에 출력 — 개발 중 디버깅용)
"""

engine = create_async_engine(settings.DATABASE_URL, echo=True)

"""
2. async_session_factory 생성
   - async_sessionmaker()를 사용해주세요
   - bind=engine (위에서 만든 엔진과 연결)
   - expire_on_commit=False (커밋 후에도 객체 속성에 접근 가능하게)
   - 이건 나중에 worker에서 세션을 만들 때 쓰는 팩토리입니다
   - 예: async with async_session_factory() as session:
"""

async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

"""   
3. get_session 함수
   - async generator 함수로 만들어주세요 (async def + yield)
   - async_session_factory()로 세션을 만들어서 yield
   - 이건 FastAPI의 Depends()에서 쓸 의존성 주입용입니다
   - 패턴:
     async def get_session():
         async with async_session_factory() as session:
             yield session
"""
async def get_session():
      async with async_session_factory() as session:
         yield session
