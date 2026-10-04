"""Store the private Meesho source URL for products.

Revision ID: 0010_product_meesho_url
Revises: 0009_telegram_notifications
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010_product_meesho_url'
down_revision: Union[str, None] = '0009_telegram_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('products', sa.Column('meesho_url', sa.Text(), nullable=True))


def downgrade() -> None:
	op.drop_column('products', 'meesho_url')