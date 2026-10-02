"""Create a sample backup table.

Revision ID: 0006_backup_table
Revises: 0005_product_details
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_backup_table'
down_revision: Union[str, None] = '0005_product_details'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'backup',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('payload', sa.JSON(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
	)


def downgrade() -> None:
	op.drop_table('backup')