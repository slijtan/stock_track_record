"""Add cancelled status to channel

Revision ID: af216f05b131
Revises: 41c683a4e8bc
Create Date: 2026-01-23 00:47:26.144491

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'af216f05b131'
down_revision: Union[str, None] = '41c683a4e8bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'cancelled' to channel_status ENUM
    op.execute("ALTER TABLE channels MODIFY COLUMN status ENUM('pending', 'processing', 'completed', 'failed', 'cancelled') DEFAULT 'pending'")


def downgrade() -> None:
    # Remove 'cancelled' from channel_status ENUM
    op.execute("ALTER TABLE channels MODIFY COLUMN status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending'")
