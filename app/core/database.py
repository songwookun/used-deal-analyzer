from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings


engine = create_async_engine(settings.DATABASE_URL, echo=True)

# expire_on_commit=False — 비동기에서 commit 후에도 객체 속성 접근 가능하게
async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session():
    async with async_session_factory() as session:
        yield session
