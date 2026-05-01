"""phase 7 past_searches table

Revision ID: 25a9c06c2ef2
Revises: 392363719077
Create Date: 2026-05-01 10:37:40.771613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25a9c06c2ef2'
down_revision: Union[str, Sequence[str], None] = '392363719077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """검색 누적 테이블 (Phase 7) — RAG 자원 + 분석 캐시."""
    op.create_table(
        "past_searches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("normalizedQuery", sa.String(length=200), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("resultsCount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medianPrice", sa.Integer(), nullable=True),
        sa.Column("keywordTrendLabel", sa.String(length=10), nullable=True),
        sa.Column("keywordChangePercent", sa.Float(), nullable=True),
        sa.Column("llmAssessment", sa.JSON(), nullable=True),
        sa.Column("rawResults", sa.JSON(), nullable=True),
        sa.Column("rawTrend", sa.JSON(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_past_searches_normalized_query",
                    "past_searches", ["normalizedQuery"])
    op.create_index("ix_past_searches_created_at",
                    "past_searches", ["createdAt"])


def downgrade() -> None:
    op.drop_index("ix_past_searches_created_at", table_name="past_searches")
    op.drop_index("ix_past_searches_normalized_query", table_name="past_searches")
    op.drop_table("past_searches")
