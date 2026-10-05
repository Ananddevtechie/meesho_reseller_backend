"""Add database-backed product image uploads.

Revision ID: 0013_product_images
Revises: 0012_order_delivery_tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013_product_images'
down_revision: Union[str, None] = '0012_order_delivery_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'product_images',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('product_id', sa.String(length=100), nullable=False),
		sa.Column('content_type', sa.String(length=40), nullable=False),
		sa.Column('image_data', sa.LargeBinary(), nullable=False),
		sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_index('ix_product_images_product_id', 'product_images', ['product_id'])


def downgrade() -> None:
	op.drop_index('ix_product_images_product_id', table_name='product_images')
	op.drop_table('product_images')
