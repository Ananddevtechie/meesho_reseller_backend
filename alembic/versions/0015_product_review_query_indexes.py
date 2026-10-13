"""Index product review lookup and image joins.

Revision ID: 0015_review_indexes
Revises: 0014_product_review_sources
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0015_review_indexes'
down_revision: Union[str, None] = '0014_product_review_sources'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_index(
		'ix_product_reviews_product_created_at',
		'product_reviews',
		['product_id', 'created_at'],
	)
	op.create_index(
		'ix_product_review_images_review_id',
		'product_review_images',
		['review_id'],
	)


def downgrade() -> None:
	op.drop_index('ix_product_review_images_review_id', table_name='product_review_images')
	op.drop_index('ix_product_reviews_product_created_at', table_name='product_reviews')
