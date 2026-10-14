"""Index product review pagination order.

Revision ID: 0016_review_pagination
Revises: 0015_review_indexes
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0016_review_pagination'
down_revision: Union[str, None] = '0015_review_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_index(
		'ix_product_reviews_product_rating_created_at',
		'product_reviews',
		['product_id', 'rating', 'created_at'],
	)


def downgrade() -> None:
	op.drop_index('ix_product_reviews_product_rating_created_at', table_name='product_reviews')
