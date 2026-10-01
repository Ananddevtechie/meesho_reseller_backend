"""Add storefront product details.

Revision ID: 0005_product_details
Revises: 0004_customer_name_phone_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005_product_details'
down_revision: Union[str, None] = '0004_customer_name_phone_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('products', sa.Column('eyebrow', sa.String(length=120), nullable=False, server_default=''))
	op.add_column('products', sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'))
	op.add_column('products', sa.Column('stock_label', sa.String(length=120), nullable=False, server_default='Available now'))
	for name in ('gallery', 'benefits', 'features', 'specifications', 'package_contents', 'faqs'):
		op.add_column('products', sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
	for name in ('faqs', 'package_contents', 'specifications', 'features', 'benefits', 'gallery'):
		op.drop_column('products', name)
	op.drop_column('products', 'stock_label')
	op.drop_column('products', 'currency')
	op.drop_column('products', 'eyebrow')