"""phase 6 category trends table

Revision ID: 392363719077
Revises: 305d970bfc06
Create Date: 2026-05-01 09:47:58.311022

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '392363719077'
down_revision: Union[str, Sequence[str], None] = '305d970bfc06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """카테고리 검색 트렌드 시계열 캐시 (Phase 6)."""
    op.create_table(
        "category_trends",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("naverCid", sa.String(length=20), nullable=False),
        sa.Column("periodStart", sa.Date(), nullable=False),
        sa.Column("periodEnd", sa.Date(), nullable=False),
        sa.Column("changePercent", sa.Float(), nullable=False),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.Column("rawSeries", sa.JSON(), nullable=True),
        sa.Column("fetchedAt", sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_category_trends_category", "category_trends", ["category"])
    op.create_index("ix_category_trends_period_end", "category_trends", ["periodEnd"])


def downgrade() -> None:
    op.drop_index("ix_category_trends_period_end", table_name="category_trends")
    op.drop_index("ix_category_trends_category", table_name="category_trends")
    op.drop_table("category_trends")
