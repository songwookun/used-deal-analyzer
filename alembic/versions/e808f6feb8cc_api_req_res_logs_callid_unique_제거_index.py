"""api_req_res_logs.callId unique 제거 → index

Revision ID: e808f6feb8cc
Revises: 8aee7b427057
Create Date: 2026-04-28 22:23:54.673772

SQLite는 ALTER COLUMN 미지원이라 UNIQUE 제거를 ORM 레벨에서 못 함.
batch_alter_table + copy_from 패턴은 alembic이 reflect한 기존 UNIQUE를 우선시해
의도대로 안 떨어짐 → raw SQL로 임시 테이블 swap 직접 수행.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e808f6feb8cc'
down_revision: Union[str, Sequence[str], None] = '8aee7b427057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_TABLE_NO_UNIQUE = """
CREATE TABLE api_req_res_logs_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "callId" VARCHAR(36) NOT NULL,
    "itemId" INTEGER,
    "apiType" VARCHAR(20) NOT NULL,
    event VARCHAR(10) NOT NULL,
    "requestBody" JSON,
    "responseBody" JSON,
    "httpStatus" INTEGER,
    "durationMs" INTEGER,
    "createdAt" DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    "updatedAt" DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL
)
"""

_NEW_TABLE_WITH_UNIQUE = """
CREATE TABLE api_req_res_logs_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "callId" VARCHAR(36) NOT NULL UNIQUE,
    "itemId" INTEGER,
    "apiType" VARCHAR(20) NOT NULL,
    event VARCHAR(10) NOT NULL,
    "requestBody" JSON,
    "responseBody" JSON,
    "httpStatus" INTEGER,
    "durationMs" INTEGER,
    "createdAt" DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    "updatedAt" DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL
)
"""

_COPY = """
INSERT INTO api_req_res_logs_new
    (id, "callId", "itemId", "apiType", event, "requestBody", "responseBody",
     "httpStatus", "durationMs", "createdAt", "updatedAt")
SELECT
    id, "callId", "itemId", "apiType", event, "requestBody", "responseBody",
    "httpStatus", "durationMs", "createdAt", "updatedAt"
FROM api_req_res_logs
"""


def upgrade() -> None:
    """callId UNIQUE 제거 + INDEX 추가."""
    op.execute(_NEW_TABLE_NO_UNIQUE)
    op.execute(_COPY)
    op.execute("DROP TABLE api_req_res_logs")
    op.execute("ALTER TABLE api_req_res_logs_new RENAME TO api_req_res_logs")
    op.execute('CREATE INDEX "ix_api_req_res_logs_callId" ON api_req_res_logs ("callId")')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "ix_api_req_res_logs_callId"')
    op.execute(_NEW_TABLE_WITH_UNIQUE)
    op.execute(_COPY)
    op.execute("DROP TABLE api_req_res_logs")
    op.execute("ALTER TABLE api_req_res_logs_new RENAME TO api_req_res_logs")
