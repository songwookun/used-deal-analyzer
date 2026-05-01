"""phase 4c retry columns

Revision ID: 305d970bfc06
Revises: e808f6feb8cc
Create Date: 2026-05-01 08:50:12.182939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '305d970bfc06'
down_revision: Union[str, Sequence[str], None] = 'e808f6feb8cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """retry 정책용 3개 컬럼 추가."""
    with op.batch_alter_table("items") as batch:
        batch.add_column(sa.Column("retryCount", sa.Integer(),
                                    nullable=False, server_default="0"))
        batch.add_column(sa.Column("nextRetryAt",
                                    sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rawInput", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.drop_column("rawInput")
        batch.drop_column("nextRetryAt")
        batch.drop_column("retryCount")
