"""increase genre string length

Revision ID: 44f1d47fea97
Revises: b3aa2f5d9c07
Create Date: 2026-09-04 00:13:24.891623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44f1d47fea97'
down_revision: Union[str, Sequence[str], None] = 'b3aa2f5d9c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'genres',
               existing_type=sa.VARCHAR(length=50),
               type_=sa.String(length=150),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'genres',
               existing_type=sa.String(length=150),
               type_=sa.VARCHAR(length=50),
               nullable=False)
