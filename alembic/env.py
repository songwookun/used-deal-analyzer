"""
[TASK-006] Alembic 비동기 마이그레이션 설정

이 파일은 alembic이 마이그레이션을 실행할 때 사용하는 설정 파일이야.
우리 프로젝트는 async SQLAlchemy를 쓰니까 run_migrations_online()을
비동기 버전으로 바꿔야 해.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

"""
[요구사항 1] target_metadata 연결

- app.models에서 Base를 import해주세요
- target_metadata = Base.metadata 로 설정
- 이래야 alembic이 우리 모델(8개 테이블)을 인식해서 자동으로 마이그레이션 생성 가능
"""
from app.models import Base
target_metadata = Base.metadata

"""
[요구사항 2] sqlalchemy.url을 config.py에서 가져오기

- app.core.config에서 settings를 import
- config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
- 이러면 alembic.ini에 DB URL 하드코딩 안 해도 됨 (.env에서 자동으로 읽힘)
"""
from app.core.config import settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

def run_migrations_offline() -> None:
    """오프라인 모드 — 이건 수정 안 해도 됨 (그대로 두세요)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

"""
[요구사항 3] run_migrations_online을 비동기로 변경

- 함수를 async def run_async_migrations()로 새로 만들어주세요
- async_engine_from_config()로 엔진 생성:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
- async with connectable.connect()로 커넥션 획득
- connection.run_sync()으로 마이그레이션 실행:
    await connection.run_sync(do_run_migrations)
- 마지막에 await connectable.dispose()

- do_run_migrations(connection) 헬퍼 함수도 만들어주세요:
    def do_run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

- run_migrations_online() 함수는 동기 함수로 유지하되,
  안에서 asyncio.run(run_async_migrations())를 호출
  → import asyncio 필요
"""
def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

async def run_async_migrations() -> None:
    """비동기 마이그레이션 실행 함수"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def do_run_migrations(connection):
    """마이그레이션 실행 헬퍼 함수"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
