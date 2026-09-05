"""add last_verification_sent_at to users

Revision ID: 331ee3cdc73c
Revises: 188ae37be4aa
Create Date: 2026-09-04 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '331ee3cdc73c'
down_revision: Union[str, Sequence[str], None] = '188ae37be4aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('last_verification_sent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'last_verification_sent_at')
