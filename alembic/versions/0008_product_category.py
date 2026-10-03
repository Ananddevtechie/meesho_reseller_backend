"""Add product categories for storefront filtering.

Revision ID: 0008_product_category
Revises: 0007_admins_table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_product_category'
down_revision: Union[str, None] = '0007_admins_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('products', sa.Column('category', sa.String(length=80), nullable=False, server_default='Other'))


def downgrade() -> None:
	op.drop_column('products', 'category')